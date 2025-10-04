from flask import Flask, request, send_file, jsonify
from anthropic import Anthropic
import os
import logging
from flask_cors import CORS
import weasyprint
from datetime import datetime
import requests
import re
import math

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

app = Flask(__name__)
CORS(app)
app.config['JSON_AS_ASCII'] = False

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

def get_google_static_map(address, city, api_key):
    """Génère et télécharge une carte Google Maps"""
    try:
        full_address = f"{address}, {city}, France"
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            return None
        
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        
        markers = f"color:red|label:P|{lat},{lng}"
        static_map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lng}&zoom=15&size=600x400&maptype=roadmap&markers={markers}&key={api_key}"
        
        map_response = requests.get(static_map_url)
        if map_response.status_code == 200:
            os.makedirs('temp', exist_ok=True)
            map_path = os.path.join('temp', f"map_{city.replace(' ', '_')}.png")
            with open(map_path, 'wb') as f:
                f.write(map_response.content)
            return os.path.abspath(map_path)
    except Exception as e:
        logging.error(f"Erreur carte: {e}")
        return None

def get_street_view_image(address, city, api_key):
    """Génère et télécharge une image Street View"""
    try:
        full_address = f"{address}, {city}, France"
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            return None
        
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        
        street_view_url = f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lng}&fov=80&heading=70&pitch=0&key={api_key}"
        
        sv_response = requests.get(street_view_url)
        if sv_response.status_code == 200:
            os.makedirs('temp', exist_ok=True)
            sv_path = os.path.join('temp', f"streetview_{city.replace(' ', '_')}.png")
            with open(sv_path, 'wb') as f:
                f.write(sv_response.content)
            return os.path.abspath(sv_path)
    except Exception as e:
        logging.error(f"Erreur Street View: {e}")
        return None

def extract_transport_lines(place, place_id, place_type, api_key):
    """Extrait les numéros de lignes de transport"""
    lines = []
    
    if not place_id:
        return lines
        
    place_details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,type,formatted_address,editorial_summary&key={api_key}"
    place_details_response = requests.get(place_details_url)
    place_details = place_details_response.json()
    
    if place_details.get('status') != 'OK':
        return lines
    
    result = place_details.get('result', {})
    name = result.get('name', '')
    address = result.get('formatted_address', '')
    
    editorial_summary = result.get('editorial_summary', {}).get('overview', '')
    if editorial_summary:
        summary_line_matches = re.findall(r'(?:ligne|bus|tram|metro|métro|train|lignes?)\s*([0-9a-zA-Z]+)', editorial_summary.lower())
        if summary_line_matches:
            lines.extend(summary_line_matches)
    
    name_match = re.findall(r'(?:bus|métro|tram|tramway|ligne|train)\s*([0-9a-zA-Z]+)', name.lower())
    if name_match:
        lines.extend(name_match)
    
    if not lines and place_type in ['bus_station', 'subway_station', 'train_station', 'transit_station']:
        clean_name = name.lower()
        for term in ['station', 'gare', 'arrêt', 'stop', place_type]:
            clean_name = clean_name.replace(term, '')
        simple_match = re.findall(r'\b([0-9a-zA-Z]{1,3})\b', clean_name)
        if simple_match:
            lines.extend(simple_match)
    
    address_match = re.findall(r'(?:bus|métro|tram|tramway|ligne)\s*([0-9a-zA-Z]+)', address.lower())
    if address_match:
        lines.extend(address_match)
    
    vicinity = place.get('vicinity', '')
    if vicinity:
        vicinity_matches = re.findall(r'(?:bus|métro|tram|tramway|ligne)\s*([0-9a-zA-Z]+)', vicinity.lower())
        if vicinity_matches:
            lines.extend(vicinity_matches)
    
    unique_lines = []
    for line in lines:
        line = line.strip().upper()
        if line and line not in unique_lines:
            unique_lines.append(line)
    
    return unique_lines

def calculate_distance(origin, destination, api_key):
    """Calcule la distance entre deux points"""
    try:
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin[0]},{origin[1]}&destinations={destination[0]},{destination[1]}&mode=walking&key={api_key}"
        response = requests.get(url)
        data = response.json()
        
        if data.get('status') == 'OK' and data.get('rows', [{}])[0].get('elements', [{}])[0].get('status') == 'OK':
            distance = data['rows'][0]['elements'][0]['distance']['text']
            duration = data['rows'][0]['elements'][0]['duration']['text']
            return distance, duration
        else:
            R = 6371000
            lat1, lon1 = origin
            lat2, lon2 = destination
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            delta_phi = math.radians(lat2 - lat1)
            delta_lambda = math.radians(lon2 - lon1)
            a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = R * c
            walking_speed = 83
            minutes = round(distance / walking_speed)
            if minutes < 60:
                duration = f"{minutes} min"
            else:
                hours = minutes // 60
                remaining_minutes = minutes % 60
                duration = f"{hours} h {remaining_minutes} min"
            return f"environ {int(distance)} m", duration
    except Exception:
        return "Distance non disponible", "Durée non disponible"

def get_google_maps_data(address, city, factors, api_key):
    """Récupère les données Google Maps pour les facteurs locaux"""
    full_address = f"{address}, {city}, France"
    logging.info(f"Recherche Google Maps pour: {full_address}, facteurs: {factors}")
    
    results = {}
    
    try:
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            logging.error(f"Erreur géocodage: {geocode_data.get('status')}")
            return {}
        
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        logging.info(f"Coordonnées: lat={lat}, lng={lng}")
        
        factor_to_place_types = {
            'transport': ['bus_station', 'subway_station', 'train_station', 'transit_station'],
            'schools': ['school', 'primary_school', 'secondary_school', 'university'],
            'shops': ['supermarket', 'shopping_mall', 'store', 'convenience_store', 'bakery', 'pharmacy'],
            'security': ['police']
        }
        
        search_radius = 2000
        
        for factor in factors:
            if factor not in factor_to_place_types:
                continue
                
            results[factor] = {}
            
            for place_type in factor_to_place_types[factor]:
                nearby_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={search_radius}&type={place_type}&key={api_key}"
                nearby_response = requests.get(nearby_url)
                nearby_data = nearby_response.json()
                
                if nearby_data.get('status') == 'OK':
                    place_results = []
                    for place in nearby_data.get('results', [])[:10]:
                        distance, duration = calculate_distance(
                            (lat, lng),
                            (place['geometry']['location']['lat'], place['geometry']['location']['lng']),
                            api_key
                        )
                        
                        place_info = {
                            'name': place['name'],
                            'distance': distance,
                            'duration': duration,
                            'rating': place.get('rating', 'Non évalué'),
                            'address': place.get('vicinity', 'Adresse non disponible')
                        }
                        
                        if factor == 'transport':
                            place_id = place.get('place_id')
                            if place_id:
                                lines = extract_transport_lines(place, place_id, place_type, api_key)
                                place_info['lines'] = lines
                                
                                transport_type = "Arrêt de transport"
                                if 'bus' in place_type or 'bus' in place['name'].lower():
                                    transport_type = "Bus"
                                elif 'subway' in place_type or 'métro' in place['name'].lower():
                                    transport_type = "Métro"
                                elif 'train' in place_type or 'gare' in place['name'].lower():
                                    transport_type = "Train"
                                elif 'tram' in place_type or 'tram' in place['name'].lower():
                                    transport_type = "Tramway"
                                
                                place_info['transport_type'] = transport_type
                        
                        place_results.append(place_info)
                    
                    if place_results:
                        results[factor][place_type] = place_results
    except Exception as e:
        logging.error(f"Erreur Google Maps data: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
    logging.info(f"Données Google Maps récupérées: {len(results)} facteurs")
    return results

def format_google_data_for_html(google_data):
    """Formate les données Google Maps en HTML pour Claude"""
    if not google_data:
        return "<p>Aucune donnée de proximité disponible.</p>"
    
    place_type_names = {
        'supermarket': 'Supermarchés',
        'shopping_mall': 'Centres commerciaux',
        'store': 'Magasins',
        'convenience_store': 'Épiceries',
        'bakery': 'Boulangeries',
        'pharmacy': 'Pharmacies',
        'school': 'Écoles',
        'primary_school': 'Écoles primaires',
        'secondary_school': 'Écoles secondaires/Collèges',
        'university': 'Universités',
        'bus_station': 'Arrêts de bus',
        'subway_station': 'Stations de métro',
        'train_station': 'Gares ferroviaires',
        'transit_station': 'Stations de transport',
        'police': 'Commissariats'
    }
    
    factor_names = {
        'transport': 'Transports en commun',
        'schools': 'Établissements scolaires',
        'shops': 'Commerces et services',
        'security': 'Sécurité'
    }
    
    html_parts = []
    
    for factor, factor_data in google_data.items():
        factor_html = f"<h3 style='color: #1e40af; margin-top: 25px;'>{factor_names.get(factor, factor)}</h3>"
        
        for place_type, places in factor_data.items():
            if places:
                factor_html += f"<h4 style='color: #64748b; margin-top: 15px;'>{place_type_names.get(place_type, place_type)}</h4>"
                factor_html += "<ul style='list-style: none; padding-left: 0;'>"
                
                for place in places[:10]:
                    factor_html += f"<li style='margin-bottom: 15px; padding: 10px; background: #f8fafc; border-left: 3px solid #3b82f6;'>"
                    factor_html += f"<strong style='color: #1e293b;'>{place['name']}</strong><br>"
                    
                    if 'distance' in place and 'duration' in place:
                        factor_html += f"<span style='color: #64748b;'>À pied: {place['distance']} ({place['duration']})</span><br>"
                    
                    if 'transport_type' in place:
                        factor_html += f"<span style='color: #64748b;'>Type: {place['transport_type']}</span><br>"
                    
                    if 'lines' in place and place['lines']:
                        lines_str = ", ".join(place['lines'])
                        factor_html += f"<span style='color: #1e40af; font-weight: 600;'>Lignes: {lines_str}</span><br>"
                    
                    if 'address' in place:
                        factor_html += f"<span style='color: #94a3b8; font-size: 9pt;'>{place['address']}</span>"
                    
                    factor_html += "</li>"
                
                factor_html += "</ul>"
        
        html_parts.append(factor_html)
    
    return "".join(html_parts)

@app.route('/', methods=['GET', 'POST', 'HEAD'])
@app.route('/generate_report', methods=['POST'])
def generate_report():
    if request.method in ['GET', 'HEAD']:
        return "API de génération de rapports immobiliers avec Claude - Prête!"
    
    try:
        form_data = request.json
        logging.info(f"Génération rapport pour: {form_data.get('name', 'Client')}")
        
        name = form_data.get('name', 'Client')
        city = form_data.get('city', 'Nice')
        address = form_data.get('address-line1', 'Non spécifié')
        email = form_data.get('agency-email', 'Non spécifié')
        phone = form_data.get('phone', 'Non spécifié')
        local_factors = form_data.get('localFactors', [])
        
        # Google Maps
        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyAqcyOXDwvgVW4eYy5vqW8TXM5FQ3DKB9w")
        map_path = get_google_static_map(address, city, api_key)
        street_view_path = get_street_view_image(address, city, api_key)
        
        # Traduire les facteurs locaux
        factor_translation = {
            'commerces': 'shops',
            'écoles': 'schools',
            'transport': 'transport',
            'sécurité': 'security'
        }
        translated_factors = [factor_translation.get(f, f) for f in local_factors]
        
        # Récupérer les données Google Places
        google_places_data = get_google_maps_data(address, city, translated_factors, api_key) if translated_factors else {}
        google_places_html = format_google_data_for_html(google_places_data)
        
        # Images HTML
        map_html = f'<img src="file://{map_path}" alt="Carte" style="width:100%; max-width:600px; height:auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" />' if map_path else '<p style="color: #94a3b8;">Carte non disponible</p>'
        street_view_html = f'<img src="file://{street_view_path}" alt="Street View" style="width:100%; max-width:600px; height:auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" />' if street_view_path else '<p style="color: #94a3b8;">Street View non disponible</p>'
        
        # Prompt MEGA complet
        mega_prompt = f"""Tu es un expert immobilier de renommée mondiale. Génère un rapport d'analyse immobilier HTML COMPLET ultra-professionnel.

🎯 OBJECTIF: Créer un rapport corporate minimaliste avec design bleu/gris, tableaux DVF, SWOT, graphiques, et Google Maps intégré.

═══════════════════════════════════════════════════════════════════════════════
📋 DONNÉES CLIENT
═══════════════════════════════════════════════════════════════════════════════
Nom: {name}
Adresse: {address}, {city}
Email: {email}
Téléphone: {phone}
Date: {datetime.now().strftime('%d/%m/%Y')}
Facteurs locaux demandés: {', '.join(local_factors) if local_factors else 'Aucun'}

═══════════════════════════════════════════════════════════════════════════════
🗺️ GOOGLE MAPS & STREET VIEW (À INTÉGRER TEL QUEL)
═══════════════════════════════════════════════════════════════════════════════
{map_html}
{street_view_html}

═══════════════════════════════════════════════════════════════════════════════
📍 FACTEURS LOCAUX - DONNÉES GOOGLE PLACES (À INTÉGRER OBLIGATOIREMENT)
═══════════════════════════════════════════════════════════════════════════════
{google_places_html}

═══════════════════════════════════════════════════════════════════════════════
📊 LES 9 SECTIONS OBLIGATOIRES (DÉTAILLÉES 500+ MOTS CHACUNE)
═══════════════════════════════════════════════════════════════════════════════

1. **INTRODUCTION** (500+ mots)
2. **CONTEXTE** (600+ mots) - Présentation de {city}
3. **SECTEUR D'INVESTISSEMENT** (700+ mots) + TABLEAU évolution prix 2020-2025
4. **ANALYSE DU MARCHÉ** (800+ mots) + TABLEAU comparatif quartiers
5. **ANALYSE DU PRODUIT** (700+ mots) + TABLEAU biens comparables
6. **FACTEURS LOCAUX IMPORTANTS** (800+ mots) - INTÉGRER LES DONNÉES GOOGLE CI-DESSUS
7. **ÉVALUATION DES RISQUES** (600+ mots) + SWOT 4 colonnes
8. **CONCLUSION ET RECOMMANDATIONS** (500+ mots)
9. **ANALYSE PRÉDICTIVE** (700+ mots) + TABLEAU projection 2025-2030

═══════════════════════════════════════════════════════════════════════════════
🎨 CSS CORPORATE ULTRA-PROFESSIONNEL (À INTÉGRER DANS <style>)
═══════════════════════════════════════════════════════════════════════════════

@page {{ size: A4; margin: 15mm; }}
body {{ font-family: Arial, sans-serif; font-size: 11pt; line-height: 1.6; color: #1a1a1a; margin: 0; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%); color: white; padding: 30px; text-align: center; margin-bottom: 30px; border-radius: 8px; }}
.header h1 {{ margin: 0; font-size: 28pt; font-weight: 300; letter-spacing: 2px; }}
.client-info {{ background: #f8fafc; border-left: 4px solid #3b82f6; padding: 20px; margin: 20px 0; }}
.section-title {{ background: #1e293b; color: white; padding: 12px 20px; font-size: 16pt; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin: 30px 0 20px 0; border-left: 6px solid #3b82f6; }}
table {{ width: 100%; border-collapse: collapse; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); page-break-inside: avoid; }}
th {{ background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%); color: white; padding: 14px 12px; text-align: left; font-weight: 600; white-space: nowrap; }}
td {{ padding: 12px; border: 1px solid #e2e8f0; background: white; vertical-align: top; }}
tr {{ page-break-inside: avoid; }}
tr:nth-child(even) td {{ background: #f8fafc; }}
.maps-container {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 30px 0; }}
.map-box {{ border: 2px solid #e2e8f0; border-radius: 8px; padding: 15px; text-align: center; background: white; }}
.swot-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
.swot-box {{ border: 2px solid #e2e8f0; border-radius: 8px; padding: 20px; background: white; }}
.swot-box.forces {{ border-left: 4px solid #10b981; }}
.swot-box.faiblesses {{ border-left: 4px solid #ef4444; }}
.swot-box.opportunites {{ border-left: 4px solid #3b82f6; }}
.swot-box.menaces {{ border-left: 4px solid #f59e0b; }}
.footer {{ margin-top: 50px; padding-top: 20px; border-top: 2px solid #e2e8f0; text-align: center; font-size: 9pt; color: #64748b; }}

═══════════════════════════════════════════════════════════════════════════════
⚠️ INSTRUCTIONS CRITIQUES
═══════════════════════════════════════════════════════════════════════════════

1. Retourne HTML COMPLET: <!DOCTYPE html><html><head><style>...</style></head><body>...</body></html>
2. Header avec: "RAPPORT D'ANALYSE IMMOBILIÈRE" + infos client
3. Les 9 sections COMPLÈTES avec tableaux
4. Section "Facteurs locaux" DOIT contenir les données Google Places ci-dessus
5. Section "Localisation" avec les 2 images Google Maps
6. SWOT en 4 colonnes (Forces/Faiblesses/Opportunités/Menaces)
7. Tableaux: Évolution prix, Comparatif quartiers, Projection 2025-2030
8. Footer: "© {datetime.now().year} P&I Investment - Rapport confidentiel"
9. PAS de markdown, UNIQUEMENT HTML

Génère maintenant:"""

        logging.info("Génération du rapport avec Claude (1 appel)...")
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,
            temperature=0.5,
            messages=[{"role": "user", "content": mega_prompt}]
        )
        
        html_content = message.content[0].text
        
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0]
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0]
        
        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_{name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
        
        logging.info("Conversion PDF...")
        weasyprint.HTML(string=html_content).write_pdf(pdf_filename)
        
        logging.info(f"Rapport généré: {pdf_filename}")
        
        return send_file(
            pdf_filename,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"rapport_{name.replace(' ', '_')}.pdf"
        )
        
    except Exception as e:
        logging.error(f"Erreur: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
