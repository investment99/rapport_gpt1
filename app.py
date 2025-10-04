from flask import Flask, request, send_file, jsonify
from anthropic import Anthropic
import os
import logging
from flask_cors import CORS
import weasyprint
from datetime import datetime
import requests
import json

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

def get_google_places_data(address, city, factors, api_key):
    """Récupère les données Google Places pour les facteurs locaux"""
    try:
        full_address = f"{address}, {city}, France"
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            return {}
        
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        
        results = {}
        
        factor_mapping = {
            'transport': ['bus_station', 'subway_station', 'train_station'],
            'schools': ['school', 'primary_school', 'secondary_school'],
            'shops': ['supermarket', 'store', 'shopping_mall'],
            'security': ['police']
        }
        
        for factor in factors:
            if factor not in factor_mapping:
                continue
            
            results[factor] = []
            
            for place_type in factor_mapping[factor]:
                nearby_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius=1000&type={place_type}&key={api_key}"
                nearby_response = requests.get(nearby_url)
                nearby_data = nearby_response.json()
                
                if nearby_data.get('status') == 'OK':
                    for place in nearby_data.get('results', [])[:5]:
                        results[factor].append({
                            'name': place['name'],
                            'address': place.get('vicinity', 'N/A'),
                            'type': place_type
                        })
        
        return results
    except Exception as e:
        logging.error(f"Erreur Google Places: {e}")
        return {}

@app.route('/', methods=['GET', 'POST', 'HEAD'])
@app.route('/generate_report', methods=['POST'])
def generate_report():
    if request.method in ['GET', 'HEAD']:
        return "API de génération de rapports immobiliers avec Claude - Prête!"
    
    try:
        form_data = request.json
        logging.info(f"Génération du rapport pour: {form_data.get('name', 'Client')}")
        
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
        places_data = get_google_places_data(address, city, local_factors, api_key)
        
        # Construction des chemins pour les images
        map_html = f'<img src="file://{map_path}" alt="Carte" style="width:100%; max-width:600px; height:auto;" />' if map_path else '<p>Carte non disponible</p>'
        street_view_html = f'<img src="file://{street_view_path}" alt="Street View" style="width:100%; max-width:600px; height:auto;" />' if street_view_path else '<p>Street View non disponible</p>'
        
        # Formatage des données Google Places
        places_formatted = ""
        for factor, places in places_data.items():
            factor_names = {
                'transport': 'Transports en commun',
                'schools': 'Établissements scolaires',
                'shops': 'Commerces',
                'security': 'Sécurité'
            }
            places_formatted += f"\n\n### {factor_names.get(factor, factor)}\n"
            for place in places[:10]:
                places_formatted += f"- **{place['name']}** - {place['address']}\n"
        
        # Prompt ULTRA-COMPLET pour Claude
        mega_prompt = f"""Tu es un expert immobilier de renommée mondiale. Génère un rapport d'analyse immobilier HTML COMPLET ultra-professionnel.

═══════════════════════════════════════════════════════
📋 DONNÉES CLIENT
═══════════════════════════════════════════════════════
Nom: {name}
Adresse analysée: {address}, {city}
Email: {email}
Téléphone: {phone}
Date: {datetime.now().strftime('%d/%m/%Y')}
Facteurs locaux demandés: {', '.join(local_factors) if local_factors else 'Aucun'}

═══════════════════════════════════════════════════════
🗺️ DONNÉES GOOGLE MAPS À INTÉGRER
═══════════════════════════════════════════════════════
Carte: {map_html}
Street View: {street_view_html}

Données lieux à proximité:
{places_formatted if places_formatted else 'Aucune donnée de proximité disponible'}

═══════════════════════════════════════════════════════
📊 LES 9 SECTIONS OBLIGATOIRES À GÉNÉRER (DÉTAILLÉES)
═══════════════════════════════════════════════════════

1. **INTRODUCTION** (500+ mots)
   - Présentation personnalisée pour {name}
   - Contexte du projet immobilier
   - Objectifs de l'analyse
   - Méthodologie utilisée

2. **CONTEXTE** (600+ mots)
   - Présentation de {city}
   - Démographie, économie, attractivité
   - Infrastructures et développement urbain
   - Tendances immobilières générales

3. **SECTEUR D'INVESTISSEMENT** (700+ mots)
   - Analyse du marché immobilier à {city}
   - Évolution des prix au m² (2020-2025) avec TABLEAU:
     | Année | Prix moyen/m² | Évolution |
     |-------|---------------|-----------|
     | 2020  | 8 500€        | -         |
     | 2021  | 8 950€        | +5.3%     |
     | 2022  | 9 400€        | +5.0%     |
     | 2023  | 9 950€        | +5.9%     |
     | 2024  | 10 500€       | +5.5%     |
     | 2025  | 11 000€       | +4.8%     |
   - Rendement locatif moyen
   - Graphique ASCII d'évolution (optionnel)

4. **ANALYSE DU MARCHÉ** (800+ mots)
   - Comparaison des quartiers de {city} avec TABLEAU:
     | Quartier | Prix/m² | Rendement | Demande |
     |----------|---------|-----------|---------|
     | Centre   | 11 000€ | 3.5%      | Forte   |
     | Nord     | 9 500€  | 4.2%      | Moyenne |
     | Sud      | 8 800€  | 4.5%      | Forte   |
     | Est      | 7 500€  | 5.0%      | Moyenne |
   - Facteurs d'influence des prix
   - Tendances actuelles du marché

5. **ANALYSE DU PRODUIT** (700+ mots)
   - Caractéristiques du bien au {address}
   - Estimation de valeur avec TABLEAU comparatif:
     | Critère | Bien analysé | Moyenne quartier | Écart |
     |---------|--------------|------------------|-------|
     | Prix/m² | 10 500€      | 10 000€          | +5%   |
     | Surface | 80 m²        | 75 m²            | +6.7% |
   - Biens comparables dans la zone
   - Potentiel de valorisation

6. **FACTEURS LOCAUX IMPORTANTS** (800+ mots)
   - **INTÉGRER LES DONNÉES GOOGLE CI-DESSUS**
   - Pour chaque facteur demandé ({', '.join(local_factors)}):
     * Liste complète des établissements/services
     * Distances et temps de trajet
     * Impact sur la valeur du bien
   - Tableaux détaillés pour chaque catégorie

7. **ÉVALUATION DES RISQUES** (600+ mots)
   - Analyse SWOT en 2 colonnes:
     | ✅ FORCES | ⚠️ FAIBLESSES |
     |-----------|---------------|
     | Liste     | Liste         |
     
     | 🎯 OPPORTUNITÉS | ⚡ MENACES |
     |-----------------|-----------|
     | Liste           | Liste     |
   - Risques de marché quantifiés
   - Stratégies de mitigation

8. **CONCLUSION ET RECOMMANDATIONS** (500+ mots)
   - Synthèse de l'analyse
   - Recommandation claire: INVESTIR ou NON
   - Conditions optimales d'acquisition
   - Points de vigilance
   - Prochaines étapes

9. **ANALYSE PRÉDICTIVE ET ARGUMENTÉE** (700+ mots)
   - Projection 2025-2030 avec TABLEAU:
     | Année | Prix prévu/m² | Évolution | Rendement |
     |-------|---------------|-----------|-----------|
     | 2025  | 11 000€       | -         | 3.8%      |
     | 2026  | 11 500€       | +4.5%     | 3.9%      |
     | 2027  | 12 100€       | +5.2%     | 4.0%      |
     | 2028  | 12 700€       | +5.0%     | 4.1%      |
     | 2029  | 13 350€       | +5.1%     | 4.2%      |
     | 2030  | 14 000€       | +4.9%     | 4.3%      |
   - Scénarios optimiste/réaliste/pessimiste
   - Meilleur type de bien pour investissement locatif

═══════════════════════════════════════════════════════
🎨 DESIGN CORPORATE ULTRA-PROFESSIONNEL OBLIGATOIRE
═══════════════════════════════════════════════════════

CSS À INTÉGRER DANS <style>:

@page {{
    size: A4;
    margin: 15mm;
}}

body {{
    font-family: 'Arial', 'Helvetica', sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a1a;
    margin: 0;
    padding: 20px;
}}

.header {{
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
    color: white;
    padding: 30px;
    text-align: center;
    margin-bottom: 30px;
    border-radius: 8px;
}}

.header h1 {{
    margin: 0;
    font-size: 28pt;
    font-weight: 300;
    letter-spacing: 2px;
}}

.header .subtitle {{
    font-size: 14pt;
    margin-top: 10px;
    opacity: 0.9;
}}

.client-info {{
    background: #f8fafc;
    border-left: 4px solid #3b82f6;
    padding: 20px;
    margin: 20px 0;
}}

.section-title {{
    background: #1e293b;
    color: white;
    padding: 12px 20px;
    font-size: 16pt;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 30px 0 20px 0;
    border-left: 6px solid #3b82f6;
}}

.section-content {{
    padding: 0 10px;
    margin-bottom: 30px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}}

th {{
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
    color: white;
    padding: 14px 12px;
    text-align: left;
    font-weight: 600;
    font-size: 10pt;
}}

td {{
    padding: 12px;
    border: 1px solid #e2e8f0;
    background: white;
}}

tr:nth-child(even) td {{
    background: #f8fafc;
}}

.maps-container {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin: 30px 0;
}}

.map-box {{
    border: 2px solid #e2e8f0;
    border-radius: 8px;
    padding: 15px;
    text-align: center;
    background: white;
}}

.map-box h3 {{
    color: #1e40af;
    margin-top: 0;
}}

.swot-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin: 20px 0;
}}

.swot-box {{
    border: 2px solid #e2e8f0;
    border-radius: 8px;
    padding: 20px;
    background: white;
}}

.swot-box h3 {{
    margin-top: 0;
    font-size: 14pt;
}}

.swot-box.forces {{ border-left: 4px solid #10b981; }}
.swot-box.faiblesses {{ border-left: 4px solid #ef4444; }}
.swot-box.opportunites {{ border-left: 4px solid #3b82f6; }}
.swot-box.menaces {{ border-left: 4px solid #f59e0b; }}

.footer {{
    margin-top: 50px;
    padding-top: 20px;
    border-top: 2px solid #e2e8f0;
    text-align: center;
    font-size: 9pt;
    color: #64748b;
}}

.highlight {{
    background: #dbeafe;
    padding: 15px;
    border-left: 4px solid #3b82f6;
    margin: 20px 0;
}}

═══════════════════════════════════════════════════════
⚠️ INSTRUCTIONS CRITIQUES
═══════════════════════════════════════════════════════

1. Retourne UN SEUL fichier HTML COMPLET avec:
   - <!DOCTYPE html>
   - <html><head> avec <style> intégré
   - <body> avec TOUT le contenu

2. INTÈGRE les images Google Maps avec les balises fournies ci-dessus

3. Génère TOUS les tableaux demandés avec des données réalistes

4. Les 9 sections DOIVENT être complètes et détaillées (pas de résumé!)

5. Utilise le design corporate fourni (bleu #1e40af, #3b82f6)

6. Ajoute un footer avec: "© {datetime.now().year} P&I Investment - Rapport confidentiel"

7. N'utilise PAS de markdown, UNIQUEMENT du HTML pur

8. Les tableaux doivent être en HTML <table>

9. INTÈGRE les données Google Places dans la section Facteurs locaux

Génère maintenant le HTML complet:"""

        logging.info("Génération du rapport complet avec Claude (1 seul appel)...")
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,
            temperature=0.5,
            messages=[{"role": "user", "content": mega_prompt}]
        )
        
        html_content = message.content[0].text
        
        # Nettoyer le HTML
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0]
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0]
        
        # Convertir en PDF
        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_{name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
        
        logging.info("Conversion HTML vers PDF...")
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
