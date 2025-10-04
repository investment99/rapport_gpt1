from flask import Flask, request, send_file, jsonify
from anthropic import Anthropic
import os
import logging
from flask_cors import CORS
import weasyprint
from datetime import datetime
import requests

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

app = Flask(__name__)
CORS(app)
app.config['JSON_AS_ASCII'] = False

# Initialisation du client Claude avec votre clé
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

def get_google_static_map(address, city, api_key, width=600, height=400):
    """Génère et télécharge une carte Google Maps"""
    try:
        full_address = f"{address}, {city}, France"
        
        # Geocoding
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            return None
        
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        
        # Carte statique
        markers = f"color:red|label:P|{lat},{lng}"
        static_map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap?"
            f"center={lat},{lng}&zoom=15&size={width}x{height}&maptype=roadmap"
            f"&markers={markers}&key={api_key}"
        )
        
        map_response = requests.get(static_map_url)
        if map_response.status_code == 200:
            os.makedirs('temp', exist_ok=True)
            map_path = os.path.join('temp', f"map_{city.replace(' ', '_')}.png")
            
            with open(map_path, 'wb') as f:
                f.write(map_response.content)
            
            return os.path.abspath(map_path)
        
    except Exception as e:
        logging.error(f"Erreur carte Google Maps: {e}")
    
        return None

def get_street_view_image(address, city, api_key, width=600, height=400):
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
        
        street_view_url = (
            f"https://maps.googleapis.com/maps/api/streetview?"
            f"size={width}x{height}&location={lat},{lng}"
            f"&fov=80&heading=70&pitch=0&key={api_key}"
        )
        
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

def generate_section_content(section_title, form_data):
    """Génère le contenu d'une section avec Claude"""
    
    name = form_data.get('name', 'Client')
    address = form_data.get('address-line1', 'Non spécifié')
    city = form_data.get('city', 'Nice')
    
    prompt = f"""Tu es un expert immobilier. Génère UNIQUEMENT le contenu texte pour la section "{section_title}" d'un rapport d'analyse immobilier.

CLIENT: {name}
ADRESSE: {address}, {city}
DONNÉES FORMULAIRE: {form_data}

SECTION À GÉNÉRER: {section_title}

INSTRUCTIONS:
- Minimum 500 mots pour cette section
- Contenu détaillé et professionnel
- Données chiffrées et analyses précises
- Retourne UNIQUEMENT le texte, sans titre de section (il sera ajouté automatiquement)
- Utilise des paragraphes clairs
- Intègre des tableaux en HTML si nécessaire pour présenter des données

Génère maintenant le contenu pour "{section_title}"."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        logging.error(f"Erreur Claude: {e}")
        return f"Contenu de {section_title} non disponible."

@app.route('/', methods=['GET', 'POST', 'HEAD'])
@app.route('/generate_report', methods=['POST'])
def generate_report():
    # Si c'est un GET ou HEAD, retourner un message d'accueil
    if request.method in ['GET', 'HEAD']:
        return "API de génération de rapports immobiliers avec Claude - Prête!"
    
    # Si c'est un POST, générer le rapport
    try:
        form_data = request.json
        logging.info(f"Génération du rapport pour: {form_data.get('name', 'Client')}")

        # Paramètres du client
        name = form_data.get('name', 'Client')
        city = form_data.get('city', 'Nice')
        address = form_data.get('address-line1', 'Non spécifié')
        email = form_data.get('agency-email', 'Non spécifié')
        phone = form_data.get('phone', 'Non spécifié')
        
        # Récupération des Google Maps
        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyAqcyOXDwvgVW4eYy5vqW8TXM5FQ3DKB9w")
        map_path = get_google_static_map(address, city, api_key)
        street_view_path = get_street_view_image(address, city, api_key)
        
        # Construction du bloc Google Maps en HTML
        maps_html = ""
        if map_path or street_view_path:
            maps_html = f"""
            <section class="section">
                <h2 class="section-title">Localisation et Environnement</h2>
                <div class="maps-grid">
                    {'<div class="map-item"><h3>Carte</h3><img src="file://' + map_path + '" alt="Carte" /></div>' if map_path else ''}
                    {'<div class="map-item"><h3>Street View</h3><img src="file://' + street_view_path + '" alt="Street View" /></div>' if street_view_path else ''}
                </div>
            </section>
            """
        
        # Les 9 sections à générer
        sections = [
            "Introduction",
            "Contexte",
            "Secteur d'investissement",
            "Analyse du marché",
            "Analyse du produit",
            "Facteurs locaux importants",
            "Évaluation des risques",
            "Conclusion et recommandations",
            "Analyse prédictive et argumentée"
        ]
        
        # Générer le contenu de chaque section
        logging.info("Génération des 9 sections avec Claude...")
        sections_html = ""
        for section_title in sections:
            logging.info(f"Génération de: {section_title}")
            content = generate_section_content(section_title, form_data)
            sections_html += f"""
            <section class="section">
                <h2 class="section-title">{section_title}</h2>
                <div class="section-content">
                    {content}
              </div>
            </section>
            """

        # Prompt pour Claude : assembler tout en HTML/CSS corporate
        logging.info("Assemblage final avec Claude...")
        final_prompt = f"""Tu es un designer corporate expert. Crée un rapport HTML complet ultra-professionnel.

DONNÉES CLIENT:
- Nom: {name}
- Adresse: {address}, {city}
- Email: {email}
- Téléphone: {phone}
- Date: {datetime.now().strftime('%d/%m/%Y')}

CONTENU DES 9 SECTIONS (À INTÉGRER TEL QUEL):
{sections_html}

GOOGLE MAPS (À INTÉGRER APRÈS LES SECTIONS):
{maps_html}

DESIGN CORPORATE OBLIGATOIRE:
- Palette: #000000 (noir), #333333 (gris foncé), #666666 (gris), #f5f5f5 (gris clair), #ffffff (blanc)
- Typographie: Arial, sans-serif
- @page: margin 10mm
- body: font-size 11pt, line-height 1.6, color #1a1a1a
- .header: border-bottom 2px solid #000, display flex, justify-content space-between
- .section-title: background #000, color #fff, padding 10px 20px, text-transform uppercase, letter-spacing 1px
- .section: margin 20px 0, page-break-inside avoid
- table: width 100%, border-collapse collapse, margin 15px 0
- th: background #f5f5f5, padding 12px, border 1px solid #ddd, font-weight 600
- td: padding 10px, border 1px solid #ddd
- .maps-grid: display grid, grid-template-columns 1fr 1fr, gap 20px
- img: max-width 100%, height auto
- .footer: margin-top 40px, padding-top 20px, border-top 1px solid #ccc, font-size 9pt, text-align center

STRUCTURE OBLIGATOIRE:
1. Header avec logo P&I Investment + infos client
2. Page de garde avec titre "RAPPORT D'ANALYSE IMMOBILIÈRE"
3. Les 9 sections fournies (SANS MODIFICATION DU CONTENU)
4. Section Google Maps
5. Footer avec mentions légales

IMPORTANT:
- Retourne un HTML COMPLET avec <!DOCTYPE html>, <html>, <head> avec <style>, et <body>
- N'utilise PAS de markdown, UNIQUEMENT du HTML pur
- Le CSS doit être intégré dans <style> dans le <head>
- Intègre TOUTES les 9 sections fournies sans résumer ni raccourcir
- Garde le bloc Google Maps tel quel
- Design minimaliste corporate noir/gris/blanc uniquement

Génère maintenant le HTML complet:"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,
            temperature=0.3,
            messages=[{"role": "user", "content": final_prompt}]
        )
        
        html_content = message.content[0].text
        
        # Nettoyer le HTML si besoin
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0]
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0]
        
        # Convertir en PDF avec WeasyPrint
        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_{name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf")
        
        logging.info("Conversion HTML vers PDF avec WeasyPrint...")
        weasyprint.HTML(string=html_content).write_pdf(pdf_filename)
        
        logging.info(f"Rapport généré avec succès: {pdf_filename}")
        
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
