from flask import Flask, request, send_file, jsonify, render_template_string
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
        budget = form_data.get('budget-ideal', 'Non spécifié')
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
🗺️ DONNÉES GOOGLE MAPS À INTÉGRER **EN HAUT DU RAPPORT**
═══════════════════════════════════════════════════════
⚠️ IMPORTANT : Les cartes Google Maps doivent apparaître IMMÉDIATEMENT après les informations client et AVANT la section 1 (Introduction) !

Utilise ce HTML EXACTEMENT (après le bloc .client-info et AVANT la section 1) :

<div class="maps-container">
  <div class="map-box">
    <h3>Localisation</h3>
    {map_html}
  </div>
  <div class="map-box">
    <h3>Vue de la rue</h3>
    {street_view_html}
  </div>
</div>

Données lieux à proximité (à utiliser dans la section 6 - Facteurs locaux):
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
   - **AJOUTE UN GRAPHIQUE ASCII** dans un bloc .chart-container :
     <div class="chart-container">
       <div class="chart-title">Évolution des prix (2020-2025)</div>
       <pre style="font-family: monospace; font-size: 9pt; line-height: 1.2;">
       11000€ ┤                                    ●
       10500€ ┤                            ●
       9950€  ┤                    ●
       9400€  ┤            ●
       8950€  ┤    ●
       8500€  ┤●
              └────────────────────────────────────
               2020 2021 2022 2023 2024 2025
       </pre>
     </div>
   - Rendement locatif moyen

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
   - **AJOUTE UNE GRILLE KPI** au début avec 4 cartes sur une ligne :
     <div class="kpi-grid">
       <div class="kpi-card"><div class="kpi-label">Prix d'acquisition estimé</div><div class="kpi-value">840K€</div></div>
       <div class="kpi-card"><div class="kpi-label">Surface habitable</div><div class="kpi-value">80 m²</div></div>
       <div class="kpi-card"><div class="kpi-label">Prix au m²</div><div class="kpi-value">10 500€</div></div>
       <div class="kpi-card"><div class="kpi-label">Rendement locatif brut</div><div class="kpi-value">4.1%</div></div>
     </div>
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
   - **AJOUTE UN GRAPHIQUE ASCII** de projection dans un bloc .chart-container
   - Scénarios optimiste/réaliste/pessimiste avec bloc .data-highlight
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
    page-break-before: always;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
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
    page-break-inside: avoid;
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

.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 15px;
    margin: 25px 0;
    page-break-inside: avoid;
}}

.kpi-card {{
    background: white;
    border-left: 3px solid #3b82f6;
    border-radius: 6px;
    padding: 15px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}}

.kpi-label {{
    font-size: 8pt;
    text-transform: uppercase;
    color: #64748b;
    letter-spacing: 1px;
    font-weight: 600;
    margin-bottom: 8px;
}}

.kpi-value {{
    font-size: 22pt;
    font-weight: 800;
    color: #1e293b;
    line-height: 1.2;
}}

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

.chart-container {{
    background: white;
    border: 2px solid #e2e8f0;
    border-radius: 8px;
    padding: 20px;
    margin: 30px 0;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    page-break-inside: avoid;
}}

.chart-title {{
    color: #1e40af;
    font-size: 14pt;
    font-weight: 600;
    margin-bottom: 15px;
    text-align: center;
}}

.section-content {{
    padding: 0 10px;
    margin-bottom: 30px;
}}

.section-content p {{
    text-align: justify;
    line-height: 1.8;
}}

.data-highlight {{
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border-left: 4px solid #0ea5e9;
    padding: 15px 20px;
    margin: 20px 0;
    border-radius: 4px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
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

10. **CHAQUE SECTION (1-9) COMMENCE SUR UNE NOUVELLE PAGE** grâce au .section-title

11. **AJOUTE DES GRAPHIQUES ASCII** dans les sections 3 et 9 avec la classe .chart-container

12. Utilise la classe .data-highlight pour mettre en valeur les données importantes

13. Texte justifié avec line-height: 1.8 pour un rendu pro

Génère maintenant le HTML complet:"""

        logging.info("Génération du rapport complet avec Claude (1 seul appel)...")
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=20000,
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

@app.route('/generate_web', methods=['POST', 'OPTIONS'])
def generate_interactive_report():
    """Route pour générer un rapport interactif HTML (pas de PDF)"""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        form_data = request.json
        logging.info(f"Génération rapport interactif pour: {form_data.get('name', 'Anonyme')}")
        
        # Extraction des données
        client_name = form_data.get('name', 'Client')
        address = form_data.get('address-line1', 'Non spécifié')
        city = form_data.get('city', 'Nice')
        email = form_data.get('agency-email', 'Non spécifié')
        phone = form_data.get('phone', 'Non spécifié')
        analysis_date = form_data.get('analysis-date', datetime.now().strftime('%d/%m/%Y'))
        investment_sector = form_data.get('investment-sector', 'IMMOBILIER')
        budget = form_data.get('budget-ideal', 'Non spécifié')
        investment_reason = form_data.get('investment-reason', 'Non spécifié')
        risk_tolerance = form_data.get('risk-tolerance', '5')
        property_type = form_data.get('type-bien-recherche', 'Non spécifié')
        surface_habitable = form_data.get('superficie-habitable', 'Non spécifié')
        nombre_chambres = form_data.get('nombre-chambres', 'Non spécifié')
        autres_pieces = ", ".join(form_data.get('autres-pieces', [])) if form_data.get('autres-pieces') else 'Aucune'
        local_factors_selected = ", ".join(form_data.get('localFactors', [])) if form_data.get('localFactors') else 'Aucun'
        
        # Google Maps
        google_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        full_address = f"{address}, {city}, France"
        
        # Génération du contenu avec Claude
        html_content = generate_interactive_html_with_claude(
            form_data, 
            full_address, 
            client_name, 
            budget,
            analysis_date,
            google_api_key
        )
        
        if not html_content:
            return jsonify({"error": "Échec génération HTML"}), 500
        
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
        
    except Exception as e:
        logging.error(f"Erreur rapport interactif: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

def generate_interactive_html_with_claude(form_data, full_address, client_name, budget, analysis_date, google_api_key):
    """Génère un rapport HTML interactif avec Claude"""
    
    client_name = form_data.get('name', 'Client')
    address = form_data.get('address-line1', 'Non spécifié')
    city = form_data.get('city', 'Nice')
    email = form_data.get('agency-email', 'Non spécifié')
    phone = form_data.get('phone', 'Non spécifié')
    investment_sector = form_data.get('investment-sector', 'IMMOBILIER')
    budget = form_data.get('budget-ideal', 'Non spécifié')
    investment_reason = form_data.get('investment-reason', 'Non spécifié')
    risk_tolerance = form_data.get('risk-tolerance', '5')
    property_type = form_data.get('type-bien-recherche', 'Non spécifié')
    surface_habitable = form_data.get('superficie-habitable', 'Non spécifié')
    nombre_chambres = form_data.get('nombre-chambres', 'Non spécifié')
    
    # Google API Key
    google_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    
    prompt = f"""
Tu es un expert immobilier qui génère des rapports interactifs HTML ULTRA-MODERNES avec animations et graphiques.

═══════════════════════════════════════════════════════
📋 DONNÉES CLIENT
═══════════════════════════════════════════════════════
Nom: {client_name}
Adresse analysée: {address}, {city}
Email: {email}
Téléphone: {phone}
Date de l'analyse: {analysis_date}
Secteur d'investissement: {investment_sector}
Budget idéal: {budget} €
Raison de l'investissement: {investment_reason}
Tolérance au risque (1-10): {risk_tolerance}
Type de bien recherché: {property_type}
Superficie habitable: {surface_habitable} m²
Nombre de chambres: {nombre_chambres}

═══════════════════════════════════════════════════════
🎨 DESIGN INTERACTIF ULTRA-MODERNE OBLIGATOIRE
═══════════════════════════════════════════════════════

Génère un rapport HTML COMPLET avec:

1. **HEADER ANIMÉ** avec dégradé bleu
2. **GOOGLE MAPS IFRAME INTERACTIF** (pas d'image statique!)
3. **GRAPHIQUES ANIMÉS Chart.js** (pas d'ASCII!)
4. **ANIMATIONS AU SCROLL** (fade-in, slide-up)
5. **TABLEAUX TRIABLES** avec hover effects
6. **KPI CARDS ANIMÉS** avec compteurs
7. **DESIGN RESPONSIVE** pour mobile

STRUCTURE HTML:

<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rapport Interactif - {client_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            overflow-x: hidden;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        
        .hero {{
            background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
            color: white;
            padding: 60px 40px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }}
        
        .hero::before {{
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 1px, transparent 1px);
            background-size: 50px 50px;
            animation: moveBackground 20s linear infinite;
        }}
        
        @keyframes moveBackground {{
            0% {{ transform: translate(0, 0); }}
            100% {{ transform: translate(50px, 50px); }}
        }}
        
        .hero h1 {{
            font-size: 48px;
            margin-bottom: 10px;
            position: relative;
            z-index: 1;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .hero p {{
            font-size: 20px;
            opacity: 0.9;
            position: relative;
            z-index: 1;
        }}
        
        .client-info {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 40px;
            background: #f8fafc;
        }}
        
        .info-card {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            border-left: 4px solid #3b82f6;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            opacity: 0;
            animation: fadeInUp 0.6s forwards;
        }}
        
        @keyframes fadeInUp {{
            from {{
                opacity: 0;
                transform: translateY(30px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .info-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 24px rgba(59, 130, 246, 0.2);
        }}
        
        .info-card h3 {{
            font-size: 12px;
            text-transform: uppercase;
            color: #64748b;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }}
        
        .info-card p {{
            font-size: 20px;
            font-weight: 700;
            color: #1e293b;
        }}
        
        .section {{
            padding: 60px 40px;
            opacity: 0;
            animation: fadeInUp 0.8s forwards;
        }}
        
        .section:nth-child(even) {{
            background: #f8fafc;
        }}
        
        .section-title {{
            font-size: 36px;
            color: #1e40af;
            margin-bottom: 30px;
            position: relative;
            padding-bottom: 15px;
        }}
        
        .section-title::after {{
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            width: 80px;
            height: 4px;
            background: linear-gradient(90deg, #3b82f6, #60a5fa);
        }}
        
        .map-container {{
            width: 100%;
            height: 500px;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0,0,0,0.15);
            margin: 30px 0;
        }}
        
        .map-container iframe {{
            width: 100%;
            height: 100%;
            border: none;
        }}
        
        .chart-container {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            margin: 30px 0;
        }}
        
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        
        .kpi-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
            transition: transform 0.3s ease;
        }}
        
        .kpi-card:hover {{
            transform: translateY(-10px) scale(1.05);
        }}
        
        .kpi-value {{
            font-size: 42px;
            font-weight: 800;
            margin: 10px 0;
        }}
        
        .kpi-label {{
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.9;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            border-radius: 12px;
            overflow: hidden;
        }}
        
        th {{
            background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s ease;
        }}
        
        th:hover {{
            background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        }}
        
        td {{
            padding: 15px;
            border-bottom: 1px solid #e2e8f0;
        }}
        
        tr:hover {{
            background: #f1f5f9;
        }}
        
        .footer {{
            background: #1e293b;
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        @media (max-width: 768px) {{
            .hero h1 {{ font-size: 32px; }}
            .section {{ padding: 40px 20px; }}
            .section-title {{ font-size: 28px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- HERO SECTION -->
        <div class="hero">
            <h1>📊 RAPPORT D'ANALYSE IMMOBILIER</h1>
            <p>Expertise Professionnelle - Analyse Interactive Complète</p>
        </div>
        
        <!-- CLIENT INFO -->
        <div class="client-info">
            <div class="info-card" style="animation-delay: 0.1s;">
                <h3>Client</h3>
                <p>{client_name}</p>
            </div>
            <div class="info-card" style="animation-delay: 0.2s;">
                <h3>Bien</h3>
                <p>{address}, {city}</p>
            </div>
            <div class="info-card" style="animation-delay: 0.3s;">
                <h3>Budget</h3>
                <p>{budget} €</p>
            </div>
            <div class="info-card" style="animation-delay: 0.4s;">
                <h3>Date</h3>
                <p>{analysis_date}</p>
            </div>
        </div>
        
        <!-- GOOGLE MAPS INTERACTIF -->
        <div class="section">
            <h2 class="section-title">📍 Localisation</h2>
            <div class="map-container">
                <iframe src="https://www.google.com/maps/embed/v1/place?key={google_api_key}&q={full_address.replace(' ', '+')}" allowfullscreen loading="lazy"></iframe>
            </div>
        </div>
        
        <!-- KPI CARDS -->
        <div class="section">
            <h2 class="section-title">📈 Indicateurs Clés</h2>
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Prix Moyen m²</div>
                    <div class="kpi-value">4 250 €</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Rentabilité</div>
                    <div class="kpi-value">4.8%</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Évolution 5 ans</div>
                    <div class="kpi-value">+18%</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Note Quartier</div>
                    <div class="kpi-value">8.5/10</div>
                </div>
            </div>
        </div>
        
        <!-- GRAPHIQUE -->
        <div class="section">
            <h2 class="section-title">📊 Évolution des Prix</h2>
            <div class="chart-container">
                <canvas id="priceChart"></canvas>
            </div>
        </div>
        
        <!-- ANALYSE DÉTAILLÉE -->
        <div class="section">
            <h2 class="section-title">🔍 Analyse Complète du Marché</h2>
            <p style="line-height: 1.8; margin-bottom: 30px;">
                Le marché immobilier de <strong>{city}</strong> présente des opportunités exceptionnelles. 
                L'analyse approfondie révèle une dynamique de croissance stable avec un excellent potentiel 
                de valorisation à moyen terme. Le secteur ciblé bénéficie d'infrastructures modernes et 
                d'un environnement résidentiel de qualité.
            </p>
            
            <h3 style="color: #1e40af; margin: 30px 0 20px 0;">Comparatif des Transactions DVF</h3>
            <table>
                <thead>
                    <tr>
                        <th>Adresse</th>
                        <th>Surface (m²)</th>
                        <th>Prix</th>
                        <th>Prix/m²</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>25 Avenue Victor Hugo</td>
                        <td>75</td>
                        <td>320 000 €</td>
                        <td>4 267 €</td>
                        <td>Mars 2024</td>
                    </tr>
                    <tr>
                        <td>18 Rue de France</td>
                        <td>82</td>
                        <td>348 000 €</td>
                        <td>4 244 €</td>
                        <td>Février 2024</td>
                    </tr>
                    <tr>
                        <td>42 Boulevard Jean Jaurès</td>
                        <td>68</td>
                        <td>289 000 €</td>
                        <td>4 250 €</td>
                        <td>Janvier 2024</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <!-- FOOTER -->
        <div class="footer">
            <p>&copy; {datetime.now().year} P&I Investment - Rapport confidentiel</p>
            <p style="margin-top: 10px; opacity: 0.7;">Généré le {analysis_date}</p>
        </div>
    </div>
    
    <script>
        // GRAPHIQUE CHART.JS
        const ctx = document.getElementById('priceChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: ['2019', '2020', '2021', '2022', '2023', '2024'],
                datasets: [{{
                    label: 'Prix moyen au m² (€)',
                    data: [3600, 3750, 3950, 4100, 4200, 4250],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4,
                    fill: true,
                    borderWidth: 3
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        display: true,
                        position: 'top'
                    }},
                    title: {{
                        display: false
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: false,
                        ticks: {{
                            callback: function(value) {{
                                return value.toLocaleString() + ' €';
                            }}
                        }}
                    }}
                }}
            }}
        }});
        
        // ANIMATIONS AU SCROLL
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if (entry.isIntersecting) {{
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }}
            }});
        }}, {{ threshold: 0.1 }});
        
        document.querySelectorAll('.section, .info-card').forEach(el => {{
            observer.observe(el);
        }});
    </script>
</body>
</html>

RETOURNE UNIQUEMENT LE HTML COMPLET, RIEN D'AUTRE !
"""
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        
        html_content = response.content[0].text
        
        # Nettoyer les balises markdown si présentes
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0]
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0]
        
        return html_content
        
    except Exception as e:
        logging.error(f"Erreur génération HTML interactif: {str(e)}")
        return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
