from flask import Flask, request, send_file, jsonify, url_for
import anthropic
import os
import logging
import ssl
import unicodedata
import re
from flask_cors import CORS
import weasyprint
from datetime import datetime
import tempfile
import requests
from markdown import markdown
from io import StringIO
from markdown2 import markdown as md_to_html
from bs4 import BeautifulSoup

ssl._create_default_https_context = ssl._create_unverified_context

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

app = Flask(__name__)
CORS(app)
app.config['JSON_AS_ASCII'] = False

def log_to_file(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("app_log.txt", "a") as log_file:
        log_file.write(f"{timestamp} - {message}\n")

@app.route('/test_key', methods=['GET'])
def test_key():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return f"Claude API Key loaded successfully: {api_key[:6]}...hidden", 200
    return "Claude API key not found", 500

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

# Prompt de design corporate pour Claude
CORPORATE_DESIGN_PROMPT = """
DESIGN REQUIS :
- Style corporate minimaliste (noir/gris/blanc uniquement)
- Typographie sobre (Arial, spacing précis)
- Mise en page institutionnelle avec grilles parfaites
- Google Maps intégrée avec iframe
- Tableaux de données comparables DVF
- Sections structurées avec headers noirs
- Fourchette de prix en 3 colonnes
- Analyse SWOT professionnelle
- Conclusion encadrée
- Footer avec mentions légales

FORMAT : HTML complet avec CSS intégré, prêt pour conversion PDF
STYLE : Sobre, institutionnel, sans couleurs vives
STRUCTURE : Sections claires, données structurées, visuellement impeccable
"""

def generate_complete_report_with_claude(form_data):
    """
    Génère un rapport complet avec Claude qui produit directement du HTML corporate
    """
    # Construire le prompt complet avec toutes les données du formulaire
    complete_prompt = f"""
    {CORPORATE_DESIGN_PROMPT}
    
    Générez un rapport immobilier professionnel complet en HTML avec CSS intégré pour les données suivantes :
    
    DONNÉES CLIENT :
    - Nom : {form_data.get('name', 'Non spécifié')}
    - Email : {form_data.get('email', 'Non spécifié')}
    - Téléphone : {form_data.get('phone', 'Non spécifié')}
    - Adresse : {form_data.get('address', 'Non spécifié')}
    - Type d'investissement : {form_data.get('investment_type', 'Non spécifié')}
    - Budget : {form_data.get('budget', 'Non spécifié')}
    - Secteur : {form_data.get('investment_sector', 'Non spécifié')}
    - Ville : {form_data.get('city', 'Non spécifié')}
    
    SECTIONS À INCLURE :
    1. Page de couverture avec logo P&I Investment
    2. Résumé exécutif
    3. Analyse de marché détaillée
    4. Estimation de bien avec données DVF
    5. Facteurs locaux (transports, écoles, commerces)
    6. Analyse SWOT
    7. Recommandations d'investissement
    8. Fourchette de prix en 3 colonnes
    9. Conclusion professionnelle
    10. Mentions légales
    
    INTÉGRATIONS REQUISES :
    - Google Maps iframe pour la localisation
    - Tableaux de données DVF comparatives
    - Graphiques de tendances de prix
    - Style corporate noir/gris/blanc uniquement
    
    Générez le HTML complet avec CSS intégré, prêt pour conversion PDF.
    """
    
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[
                {"role": "user", "content": complete_prompt}
            ]
        )
        
        html_content = response.content[0].text
        
        # Extraire le HTML si Claude l'a mis dans des balises markdown
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0]
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0]
            
        return html_content
        
    except Exception as e:
        logging.error(f"Erreur lors de la génération avec Claude : {str(e)}")
        return None

def html_to_pdf(html_content, output_path):
    """
    Convertit le HTML en PDF avec WeasyPrint
    """
    try:
        # Ajouter les Google Maps et améliorer le CSS si nécessaire
        enhanced_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .corporate-header {{
                    background: #000;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .section {{
                    margin: 20px 0;
                    page-break-inside: avoid;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 10px 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #f5f5f5;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Convertir en PDF
        weasyprint.HTML(string=enhanced_html).write_pdf(output_path)
        return True
        
    except Exception as e:
        logging.error(f"Erreur lors de la conversion HTML vers PDF : {str(e)}")
        return False

def clean_text(text):
    # Conserver les caractères accentués
    text = ''.join(c for c in unicodedata.normalize('NFC', text) if unicodedata.category(c)[0] != 'M')
    
    replacements = {
        '€': 'EUR', '£': 'GBP', '©': '(c)', '®': '(R)', '™': '(TM)',
        '…': '...', '—': '-', '–': '-', '"': '"', '"': '"', "'": "'", "'": "'",
    }
    
    # Appliquer les remplacements
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Supprimer les caractères non imprimables
    text = ''.join(c for c in text if c.isprintable() or c.isspace())
    
    return text

from markdown2 import markdown as md_to_html
from bs4 import BeautifulSoup

def markdown_to_elements(md_text):
    """
    Cette fonction n'est plus utilisée avec Claude mais gardée pour compatibilité
    """
    return md_text

def add_section_title(elements, title):
    """
    Cette fonction n'est plus utilisée avec Claude mais gardée pour compatibilité
    """
    pass

def generate_section(client, section_prompt, max_tokens=1700):
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=max_tokens,
        messages=[
            {"role": "user", "content": f"Vous êtes un expert de renommée mondiale en analyse financière et immobilière, spécialisé dans l'immobilier résidentiel et commercial. En tant qu'expert, votre tâche est de générer un rapport détaillé et professionnel intégrant des données chiffrées comme le prix moyen au mètre carré, l'évolution des prix sur plusieurs années ou encore le rendement locatif. Fournissez des analyses spécifiques comme l'impact des établissements scolaires, la qualité des infrastructures disponibles, et tout autre élément pertinent. Incluez des tableaux et graphiques pour une représentation visuelle des données ainsi que des recommandations de quartiers adaptées aux critères du client et aux objectifs qu'il souhaite atteindre. Analysez les tendances du marché et prévoyez les évolutions à moyen et long terme. Le rapport devra être rigoureusement adapté aux critères spécifiques du client et aux caractéristiques locales de la ville ou du bien mentionné tout en adoptant un style clair, précis et professionnel démontrant une parfaite maîtrise des enjeux économiques et sectoriels.\n\n{section_prompt}"}
        ]
    )
    return response.content[0].text

def generate_market_data(investment_sector, city):
    if investment_sector.lower() == "immobilier":
        city_data = {
            "Nice": {
                "prix_moyen": {
                    "Mont Boron": 8241,
                    "Carré d'Or": 7500,
                    "Cimiez": 5324,
                    "Musiciens": 5604,
                    "Libération": 5940,
                    "Riquier": 4633
                },
                "evolution_prix": 5.4,
                "quartiers_developpement": ["Saint-Isidore", "Le Port"],
                "segmentation": {
                    "Biens de prestige": 35,
                    "Biens intermédiaires": 50,
                    "Logements abordables": 15
                }
            },
        }
        return city_data.get(city, {})
    else:
        return {}

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        return generate_report()
    return "Bienvenue sur le serveur Flask. L'API est prête à recevoir des requêtes !"

def resize_image(image_path, output_path, target_size=(469, 716)):
    with PILImage.open(image_path) as img:
        img = img.resize(target_size, PILImage.LANCZOS)
        img.save(output_path)

def get_google_static_map(address, city, api_key, width=600, height=400, zoom=15, maptype='roadmap'):
    """
    Génère une URL pour une carte statique Google Maps de l'adresse spécifiée.
    Si possible, télécharge l'image et renvoie le chemin du fichier local.
    
    Args:
        address: L'adresse de la propriété
        city: La ville
        api_key: Clé API Google Maps
        width: Largeur de l'image en pixels
        height: Hauteur de l'image en pixels
        zoom: Niveau de zoom (1-20)
        maptype: Type de carte (roadmap, satellite, hybrid, terrain)
        
    Returns:
        Le chemin vers l'image téléchargée ou None en cas d'erreur
    """
    try:
        # Adresse complète pour la géolocalisation
        full_address = f"{address}, {city}, France"
        logging.info(f"Génération de carte pour l'adresse : {full_address}")
        
        # 1. Obtenir les coordonnées de l'adresse
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            logging.error(f"Erreur de géocodage: {geocode_data.get('status')}")
            return None
        
        # Extraction des coordonnées
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        
        # 2. Générer l'URL de la carte statique
        markers = f"color:red|label:P|{lat},{lng}"
        static_map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap?"
            f"center={lat},{lng}&zoom={zoom}&size={width}x{height}&maptype={maptype}"
            f"&markers={markers}&key={api_key}"
        )
        
        # 3. Télécharger l'image
        map_response = requests.get(static_map_url)
        if map_response.status_code == 200:
            # Créer un dossier temporaire s'il n'existe pas
            os.makedirs('temp', exist_ok=True)
            map_path = os.path.join('temp', f"map_{address.replace(' ', '_')}_{city}.png")
            
            with open(map_path, 'wb') as f:
                f.write(map_response.content)
            
            logging.info(f"Carte générée avec succès : {map_path}")
            return map_path
        else:
            logging.error(f"Erreur lors du téléchargement de la carte: {map_response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Erreur lors de la génération de la carte: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return None

def get_street_view_image(address, city, api_key, width=600, height=400):
    """
    Génère une URL pour une image Street View de l'adresse spécifiée.
    Si possible, télécharge l'image et renvoie le chemin du fichier local.
    
    Args:
        address: L'adresse de la propriété
        city: La ville
        api_key: Clé API Google Maps
        width: Largeur de l'image en pixels
        height: Hauteur de l'image en pixels
        
    Returns:
        Le chemin vers l'image téléchargée ou None en cas d'erreur
    """
    try:
        # Adresse complète pour la géolocalisation
        full_address = f"{address}, {city}, France"
        logging.info(f"Génération d'image Street View pour l'adresse : {full_address}")
        
        # 1. Obtenir les coordonnées de l'adresse
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            logging.error(f"Erreur de géocodage pour Street View: {geocode_data.get('status')}")
            return None
        
        # Extraction des coordonnées
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        
        # 2. Générer l'URL de l'image Street View
        street_view_url = (
            f"https://maps.googleapis.com/maps/api/streetview?"
            f"size={width}x{height}&location={lat},{lng}"
            f"&fov=80&heading=70&pitch=0&key={api_key}"
        )
        
        # 3. Télécharger l'image
        sv_response = requests.get(street_view_url)
        if sv_response.status_code == 200:
            # Créer un dossier temporaire s'il n'existe pas
            os.makedirs('temp', exist_ok=True)
            sv_path = os.path.join('temp', f"streetview_{address.replace(' ', '_')}_{city}.png")
            
            with open(sv_path, 'wb') as f:
                f.write(sv_response.content)
            
            logging.info(f"Image Street View générée avec succès : {sv_path}")
            return sv_path
        else:
            logging.error(f"Erreur lors du téléchargement de l'image Street View: {sv_response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Erreur lors de la génération de l'image Street View: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return None

def generate_final_pdf_with_claude(form_data, sections_content, google_maps_data=None):
    """
    Utilise Claude pour assembler tous les contenus en PDF avec style corporate
    """
    # Préparer le contenu complet
    complete_content = f"""
    DONNÉES CLIENT :
    - Nom : {form_data.get('name', 'Non spécifié')}
    - Email : {form_data.get('email', 'Non spécifié')}  
    - Téléphone : {form_data.get('phone', 'Non spécifié')}
    - Adresse : {form_data.get('address', 'Non spécifié')}
    - Ville : {form_data.get('city', 'Non spécifié')}
    - Secteur : {form_data.get('investment_sector', 'Non spécifié')}
    - Budget : {form_data.get('budget', 'Non spécifié')}
    
    CONTENU DES SECTIONS ANALYSÉES :
    {sections_content}
    
    CARTES GOOGLE MAPS :
    {google_maps_data if google_maps_data else 'Données de localisation à intégrer'}
    """
    
    # Prompt avec vos exigences de design corporate
    corporate_prompt = f"""
    Créez un rapport PDF professionnel en HTML avec CSS intégré en utilisant ce contenu analysé :
    
    {complete_content}
    
    DESIGN REQUIS :
    - Style corporate minimaliste (noir/gris/blanc uniquement)
    - Typographie sobre (Arial, spacing précis)
    - Mise en page institutionnelle avec grilles parfaites
    - Google Maps intégrée avec iframe
    - Tableaux de données comparables DVF
    - Sections structurées avec headers noirs
    - Fourchette de prix en 3 colonnes
    - Analyse SWOT professionnelle
    - Conclusion encadrée
    - Footer avec mentions légales
    
    FORMAT : HTML complet avec CSS intégré, prêt pour conversion PDF
    STYLE : Sobre, institutionnel, sans couleurs vives
    STRUCTURE : Sections claires, données structurées, visuellement impeccable
    
    Utilisez EXACTEMENT le contenu fourni ci-dessus, ne générez pas de nouveau contenu.
    """
    
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{"role": "user", "content": corporate_prompt}]
        )
        
        html_content = response.content[0].text
        
        # Extraire le HTML si nécessaire
        if "```html" in html_content:
            html_content = html_content.split("```html")[1].split("```")[0]
        elif "```" in html_content:
            html_content = html_content.split("```")[1].split("```")[0]
            
        return html_content
        
    except Exception as e:
        logging.error(f"Erreur génération PDF final avec Claude : {str(e)}")
        return None

@app.route('/generate_report', methods=['POST'])
def generate_report():
    try:
        logging.info("Requête reçue à /generate_report")
        log_to_file("Début de la génération du rapport")
        form_data = request.json
        logging.debug(f"Données reçues : {form_data}")
        log_to_file(f"Données du formulaire reçues : {form_data}")

        name = form_data.get('name', 'Client')
        analysis_date = form_data.get('analysis-date', 'Non précisé')
        investment_sector = form_data.get('investment-sector', 'Non précisé')
        address = form_data.get('address-line1', 'Non spécifié')
        email = form_data.get('agency-email', 'Non spécifié')
        phone = form_data.get('phone', 'Non spécifié')
        city = form_data.get('city', 'Nice')

        # Garder la langue (vos prompts existants)
        language = form_data.get('language', 'fr')
        language_mapping = {
            'fr': 'Français',
            'en': 'Anglais',
        }
        language_name = language_mapping.get(language, 'Français')

        client_info = {key: value for key, value in form_data.items()}
        market_data = generate_market_data(investment_sector, city)

        summary = "Résumé des informations fournies par le client :\n\n"
        for key, value in client_info.items():
            summary += f"{key}: {value}\n"

        market_data_str = f"\nDonnées spécifiques du marché :\n{market_data}\n"

        # VOS SECTIONS EXCELLENTES (gardées !)
        sections = [
            ("Introduction", 200),
            ("Contexte", 250),
            ("Secteur d'investissement", 400),
            ("Analyse du marché", 500),
            ("Analyse du produit", 500),
            ("Facteurs locaux importants", 500),
            ("Évaluation des risques", 450),
            ("Conclusion et recommandations", 500),
            ("Analyse prédictive et argumentée", 500)
        ]

        # Générer toutes les sections avec VOS prompts excellents
        sections_content = ""
        
        # Google Maps (gardé !)
        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyAqcyOXDwvgVW4eYy5vqW8TXM5FQ3DKB9w")
        google_maps_data = ""
        
        if address and address != 'Non spécifié':
            logging.info(f"Génération de la carte pour l'adresse : {address}")
            map_path = generate_static_map(address, api_key)
            street_view_path = generate_street_view_image(address, api_key)
            google_maps_data = f"Carte : {map_path}, Street View : {street_view_path}"

        # Générer chaque section avec VOS prompts
        for section_name, max_tokens in sections:
            section_prompt = f"{summary}{market_data_str}\n\nPour la section '{section_name}' :"
            
            if section_name == "Analyse du marché":
                section_prompt += f"\n\nUtilisez ces données de marché spécifiques pour {city} :\n{market_data}"
            elif section_name == "Facteurs locaux importants":
                local_factors_prompt = process_local_factors(form_data)
                section_prompt = f"{summary}{market_data_str}\n\nPour la section '{section_name}' : {local_factors_prompt}"
            
            # Utiliser VOS prompts excellents
            section_content = generate_section(client, section_prompt, max_tokens)
            sections_content += f"\n\n## {section_name}\n{section_content}\n"
            
        # Maintenant, Claude assemble tout en PDF corporate
        logging.info("Assemblage final avec Claude...")
        html_content = generate_final_pdf_with_claude(form_data, sections_content, google_maps_data)
        
        if not html_content:
            return jsonify({"error": "Erreur lors de l'assemblage final"}), 500
        
        # Convertir HTML en PDF
        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_{name.replace(' ', '_')}.pdf")
        
        if html_to_pdf(html_content, pdf_filename):
            logging.info(f"Rapport généré avec succès : {pdf_filename}")
            log_to_file(f"Rapport généré avec succès : {pdf_filename}")
            return send_file(pdf_filename, as_attachment=True)
        else:
            return jsonify({"error": "Erreur lors de la conversion PDF"}), 500
            
    except Exception as e:
        logging.error(f"Erreur lors de la génération du rapport : {str(e)}")
        log_to_file(f"Erreur lors de la génération du rapport : {str(e)}")
        return jsonify({"error": f"Erreur lors de la génération du rapport : {str(e)}"}), 500

# Configuration de l'API Google Maps
os.environ["GOOGLE_MAPS_API_KEY"] = "AIzaSyAqcyOXDwvgVW4eYy5vqW8TXM5FQ3DKB9w"

def extract_transport_lines(place, place_id, place_type, api_key):
    """
    Fonction améliorée pour extraire les numéros de lignes de transport à partir
    des données Google Maps.
    
    Cette version utilise plusieurs méthodes pour maximiser la détection des numéros de lignes:
    1. Recherche dans le nom de la station (pattern spécifique avec "bus", "métro", etc.)
    2. Recherche dans l'adresse complète de la station
    3. Extraction de simples codes alphanumériques qui pourraient être des lignes
    
    Args:
        place: Dictionnaire contenant les informations du lieu
        place_id: L'identifiant Google Place ID
        place_type: Type de lieu (bus_station, subway_station, etc.)
        api_key: Clé API Google Maps
        
    Returns:
        Liste des numéros de lignes détectés
    """
    lines = []
    
    if not place_id:
        return lines
        
    # Obtenir plus de détails sur le lieu
    place_details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,type,formatted_address,editorial_summary&key={api_key}"
    place_details_response = requests.get(place_details_url)
    place_details = place_details_response.json()
    
    if place_details.get('status') != 'OK':
        logging.warning(f"Impossible d'obtenir les détails pour le lieu {place.get('name')}")
        return lines
    
    # Extraire les informations détaillées
    result = place_details.get('result', {})
    name = result.get('name', '')
    address = result.get('formatted_address', '')
    
    # 1. Vérifier s'il y a un résumé éditorial qui pourrait contenir des informations sur les lignes
    editorial_summary = result.get('editorial_summary', {}).get('overview', '')
    if editorial_summary:
        # Chercher des mentions de lignes dans le résumé
        summary_line_matches = re.findall(r'(?:ligne|bus|tram|metro|métro|train|lignes?)\s*([0-9a-zA-Z]+)', editorial_summary.lower())
        if summary_line_matches:
            lines.extend(summary_line_matches)
    
    # 2. Rechercher les numéros de lignes dans le nom (ex: "Bus 67", "Métro 13")
    # Pattern plus large pour capturer différentes syntaxes
    name_match = re.findall(r'(?:bus|métro|tram|tramway|ligne|train)\s*([0-9a-zA-Z]+)', name.lower())
    if name_match:
        lines.extend(name_match)
    
    # 3. Si pas de lignes trouvées par les méthodes précédentes, chercher des codes alphanumériques isolés
    # qui pourraient être des lignes de transport
    if not lines and place_type in ['bus_station', 'subway_station', 'train_station', 'transit_station']:
        # Nettoyer le nom pour enlever le type de station
        clean_name = name.lower()
        for term in ['station', 'gare', 'arrêt', 'stop', place_type]:
            clean_name = clean_name.replace(term, '')
            
        # Chercher des codes qui ressemblent à des numéros de ligne (1-3 caractères alphanumériques)
        simple_match = re.findall(r'\b([0-9a-zA-Z]{1,3})\b', clean_name)
        if simple_match:
            lines.extend(simple_match)
    
    # 4. Rechercher les numéros de lignes dans l'adresse
    address_match = re.findall(r'(?:bus|métro|tram|tramway|ligne)\s*([0-9a-zA-Z]+)', address.lower())
    if address_match:
        lines.extend(address_match)
    
    # 5. Recherche dans la vicinity (disponible directement dans le place)
    vicinity = place.get('vicinity', '')
    if vicinity:
        vicinity_matches = re.findall(r'(?:bus|métro|tram|tramway|ligne)\s*([0-9a-zA-Z]+)', vicinity.lower())
        if vicinity_matches:
            lines.extend(vicinity_matches)
    
    # Éliminer les doublons et nettoyer les résultats
    unique_lines = []
    for line in lines:
        line = line.strip().upper()  # Standardisation en majuscules
        if line and line not in unique_lines:
            unique_lines.append(line)
    
    logging.info(f"Lignes de transport trouvées pour {name}: {unique_lines}")
    return unique_lines

def get_google_maps_data(address, city, factors):
    """
    Récupère des données précises depuis l'API Google Maps pour une adresse
    et les facteurs locaux spécifiés.
    """
    # Clé API Google Maps
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyAqcyOXDwvgVW4eYy5vqW8TXM5FQ3DKB9w")
    
    # Adresse complète pour la géolocalisation
    full_address = f"{address}, {city}, France"
    logging.info(f"Recherche pour l'adresse : {full_address}")
    logging.info(f"Facteurs recherchés : {factors}")
    
    # Dictionnaire pour stocker les résultats
    results = {}
    
    try:
        # 1. Obtenir les coordonnées de l'adresse
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={api_key}"
        logging.debug(f"URL geocoding : {geocode_url}")
        geocode_response = requests.get(geocode_url)
        geocode_data = geocode_response.json()
        
        if geocode_data.get('status') != 'OK':
            logging.error(f"Erreur de géocodage: {geocode_data.get('status')}")
            logging.error(f"Réponse complète: {geocode_data}")
            return {}
        
        # Extraction des coordonnées
        location = geocode_data['results'][0]['geometry']['location']
        lat, lng = location['lat'], location['lng']
        logging.info(f"Coordonnées obtenues: lat={lat}, lng={lng}")
        
        # 2. Pour chaque facteur, rechercher les lieux pertinents
        # Mapping des facteurs avec les types de lieux Google Maps
        factor_to_place_types = {
            'shops': ['supermarket', 'shopping_mall', 'store', 'convenience_store', 'bakery', 'pharmacy'],
            'schools': ['school', 'primary_school', 'secondary_school', 'university'],
            'transport': ['bus_station', 'subway_station', 'train_station', 'transit_station'],
            'security': ['police']
        }
        
        # Augmenter le rayon de recherche à 2000 mètres pour trouver plus de lieux
        search_radius = 2000
        
        # Rechercher les lieux pour chaque facteur
        for factor in factors:
            logging.info(f"Traitement du facteur : {factor}")
            if factor not in factor_to_place_types:
                logging.warning(f"Facteur non reconnu : {factor}")
                continue
                
            results[factor] = {}
            
            for place_type in factor_to_place_types.get(factor, []):
                logging.info(f"Recherche de lieux de type : {place_type}")
                # Recherche des lieux à proximité
                nearby_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius={search_radius}&type={place_type}&key={api_key}"
                logging.debug(f"URL nearby search : {nearby_url}")
                nearby_response = requests.get(nearby_url)
                nearby_data = nearby_response.json()
                
                if nearby_data.get('status') == 'OK':
                    logging.info(f"Nombre de résultats pour {place_type}: {len(nearby_data.get('results', []))}")
                    # Stocker les résultats par type de lieu
                    place_results = []
                    # Augmenter le nombre maximal de résultats à 10
                    for place in nearby_data.get('results', [])[:10]:
                        # Calculer la distance et la durée à pied
                        distance, duration = calculate_distance((lat, lng), 
                                  (place['geometry']['location']['lat'], 
                                   place['geometry']['location']['lng']), api_key)
                        
                        place_info = {
                            'name': place['name'],
                            'distance': distance,
                            'duration': duration,
                            'rating': place.get('rating', 'Non évalué'),
                            'address': place.get('vicinity', 'Adresse non disponible')
                        }
                        
                        # Extraire les numéros de lignes pour les transports
                        if factor == 'transport':
                            place_id = place.get('place_id')
                            # Utiliser la fonction améliorée pour extraire les lignes de transport
                            if place_id:
                                lines = extract_transport_lines(place, place_id, place_type, api_key)
                                place_info['lines'] = lines
                                
                                # Détecter le type de transport
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
                        logging.debug(f"Lieu trouvé: {place['name']}")
                    
                    if place_results:
                        results[factor][place_type] = place_results
                else:
                    logging.error(f"Erreur API nearby search: {nearby_data.get('status')}")
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des données Google Maps: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
    logging.info(f"Résultats finaux: {results}")
    return results

def calculate_distance(origin, destination, api_key):
    """
    Calcule la distance approximative en mètres entre deux points.
    """
    try:
        # URL de l'API Distance Matrix
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin[0]},{origin[1]}&destinations={destination[0]},{destination[1]}&mode=walking&key={api_key}"
        
        response = requests.get(url)
        data = response.json()
        
        if data.get('status') == 'OK' and data.get('rows', [{}])[0].get('elements', [{}])[0].get('status') == 'OK':
            # Distance en mètres
            distance = data['rows'][0]['elements'][0]['distance']['text']
            # Récupérer également la durée à pied
            duration = data['rows'][0]['elements'][0]['duration']['text']
            return distance, duration
        else:
            # Si l'API échoue, calculer approximativement
            import math
            
            # Rayon de la Terre en mètres
            R = 6371000
            
            # Convertir les coordonnées en radians
            lat1, lon1 = origin
            lat2, lon2 = destination
            
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            delta_phi = math.radians(lat2 - lat1)
            delta_lambda = math.radians(lon2 - lon1)
            
            # Formule de Haversine
            a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            
            # Distance en mètres
            distance = R * c
            
            # Approximation de la durée (vitesse moyenne de marche ~5 km/h = ~83 m/min)
            walking_speed = 83  # mètres par minute
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

def format_google_data_for_prompt(google_data):
    """
    Formate les données Google Maps pour les inclure dans le prompt.
    """
    if not google_data:
        return "Aucune donnée précise n'est disponible pour cette adresse."
    
    # Dictionnaire de traduction pour les types de lieux
    place_type_names = {
        'supermarket': 'Supermarché',
        'shopping_mall': 'Centre commercial',
        'store': 'Magasin',
        'convenience_store': 'Épicerie',
        'bakery': 'Boulangerie',
        'pharmacy': 'Pharmacie',
        'school': 'École',
        'primary_school': 'École primaire',
        'secondary_school': 'École secondaire/Collège',
        'university': 'Université',
        'bus_station': 'Arrêt de bus',
        'subway_station': 'Station de métro',
        'train_station': 'Gare ferroviaire',
        'transit_station': 'Station de transport',
        'light_rail_station': 'Station de tramway',
        'tram_station': 'Station de tramway',
        'police': 'Commissariat'
    }
    
    formatted_data = []
    
    for factor, factor_data in google_data.items():
        factor_text = ""
        if factor == 'shops':
            factor_text += "## **Commerces et services de proximité**\n\n"
        elif factor == 'schools':
            factor_text += "## **Établissements éducatifs**\n\n"
        elif factor == 'transport':
            factor_text += "## **Transports en commun**\n\n"
        elif factor == 'security':
            factor_text += "## **Sécurité**\n\n"
        
        # Compteur pour limiter le nombre d'éléments par facteur
        items_count = 0
        max_items = 10  # Augmentation à 10 éléments par facteur
        
        for place_type, places in factor_data.items():
            if places:
                factor_text += f"### {place_type_names.get(place_type, place_type)}\n\n"
                for place in places:
                    # Vérifier si on a atteint la limite d'éléments par facteur
                    if items_count >= max_items:
                        break
                    
                    # Format structuré sur plusieurs lignes comme demandé
                    factor_text += f"**{place['name']}**\n"
                    
                    # Ajouter la distance et durée à pied avec une ligne séparée
                    if 'distance' in place and 'duration' in place:
                        factor_text += f"À pied : {place['distance']} ({place['duration']})\n"
                    
                    # Type d'établissement
                    if 'transport_type' in place and place['transport_type']:
                        factor_text += f"Type : {place['transport_type']}\n"
                    
                    # Ajouter les numéros de lignes pour les transports
                    if 'lines' in place and place['lines']:
                        lines_str = ", ".join(place['lines'])
                        factor_text += f"Lignes : {lines_str}\n"
                    
                    # Ajouter l'adresse si disponible
                    if 'address' in place and place['address']:
                        factor_text += f"Adresse : {place['address']}\n"
                    
                    # Ajouter une ligne vide entre chaque établissement
                    factor_text += "\n"
                    
                    items_count += 1
                
                # Si on a atteint la limite, arrêter de traiter les autres types de lieux pour ce facteur
                if items_count >= max_items:
                    break
        
        if factor_text:
            formatted_data.append(factor_text)
    
    return "\n".join(formatted_data)

def improved_local_factors_with_google_maps(form_data):
    """
    Version améliorée qui utilise Google Maps API pour obtenir des données réelles.
    """
    if not form_data.get('localFactors'):
        return ""
    
    # Extraire adresse et ville
    address = form_data.get('address-line1', '')
    city = form_data.get('city', '')
    selected_factors = form_data.get('localFactors', [])
    
    # Traduire les facteurs du français à l'anglais
    factor_translation = {
        'commerces': 'shops',
        'écoles': 'schools',
        'transport': 'transport',
        'sécurité': 'security'
    }
    
    # Traduire les facteurs sélectionnés
    translated_factors = []
    for factor in selected_factors:
        if factor in factor_translation:
            translated_factors.append(factor_translation[factor])
        else:
            # Si pas de traduction, conserver tel quel
            translated_factors.append(factor)
    
    # Récupérer les données Google Maps
    google_data = get_google_maps_data(address, city, translated_factors)
    
    # Déboguer pour vérifier les données récupérées
    logging.info(f"Données Google Maps récupérées pour {address}, {city}: {google_data}")
    
    # Formater les données pour le prompt
    formatted_google_data = format_google_data_for_prompt(google_data)
    
    # Déboguer pour vérifier les données formatées
    logging.info(f"Données Google Maps formatées: {formatted_google_data}")
    
    # Liste des facteurs sélectionnés en français pour les instructions
    facteurs_selectionnes = []
    for factor in selected_factors:
        if factor == 'commerces':
            facteurs_selectionnes.append("Commerces et services de proximité")
        elif factor == 'écoles':
            facteurs_selectionnes.append("Établissements éducatifs")
        elif factor == 'transport':
            facteurs_selectionnes.append("Transports en commun")
        elif factor == 'sécurité':
            facteurs_selectionnes.append("Sécurité")

    # Créer le prompt avec les données réelles
    local_factors_prompt = f"""

# FACTEURS LOCAUX IMPORTANTS

Le client accorde une importance particulière aux facteurs suivants pour l'adresse {address}, {city}. Voici les données précises obtenues:

{formatted_google_data}

**INSTRUCTIONS IMPÉRATIVES POUR FORMATER LE TEXTE CORRECTEMENT:**

⚠️ ATTENTION - CONSIGNES CRITIQUES ET OBLIGATOIRES ⚠️

1. VOUS DEVEZ ABSOLUMENT INCLURE TOUTES LES DONNÉES CI-DESSUS DANS VOTRE RÉPONSE.
   - NE RÉSUMEZ PAS les informations
   - NE CONDENSEZ PAS les données
   - COPIEZ INTÉGRALEMENT tous les établissements de chaque catégorie
   - Il est STRICTEMENT INTERDIT de remplacer la liste détaillée par un résumé

2. STRUCTURE OBLIGATOIRE - INCLURE UNIQUEMENT LES CATÉGORIES SUIVANTES SÉLECTIONNÉES PAR LE CLIENT:
   {", ".join(facteurs_selectionnes)}
   - N'AJOUTEZ AUCUNE AUTRE CATÉGORIE QUE CELLES LISTÉES CI-DESSUS
   - NE CRÉEZ PAS DE NOUVELLES SECTIONS QUI N'EXISTENT PAS DANS LES DONNÉES

3. FORMAT EXACT ET UNIFORME REQUIS POUR CHAQUE ÉTABLISSEMENT:
   a) Nom d'établissement en gras: "**Intermarché Nice Gare du Sud**"
   b) Sur la ligne suivante: "À pied : X.X km (XX mins)"
   c) Si c'est un transport, sur la ligne suivante: "Type : Bus/Métro/Train/etc."
   d) Si c'est un transport, sur la ligne suivante: "Lignes : X, Y, Z" (même s'il n'y a qu'une seule ligne)
   e) Sur la ligne suivante: "Adresse : adresse complète"
   f) Une ligne vide entre chaque établissement

4. INSTRUCTION SPÉCIALE POUR LES TRANSPORTS:
   - Si des numéros de lignes de bus/métro/tram sont manquants, AJOUTEZ-LES
   - Format: "Lignes : 7, 9, 16, 20" (ou lettres comme "A, B, C" pour certains réseaux)
   - NE MODIFIEZ PAS les autres informations (distances, adresses, etc.)

5. EXEMPLE PRÉCIS DE MISE EN PAGE ATTENDUE:
```
**Commerces et services de proximité**

**Supermarché**

**Intermarché Nice Gare du Sud**
À pied : 0.4 km (6 mins)
Adresse : 4 All. Philippe Seguin, 06000 Nice, France

**MONOPRIX**
À pied : 0.8 km (11 mins)
Adresse : 30 Rue Biscarra, 06000 Nice, France

**Transports en commun**

**Arrêt de bus**

**Gambetta**
À pied : 0.8 km (12 mins)
Type : Bus
Lignes : 7, 8, 30, 70
Adresse : 06100 Nice, France
```

⚠️ CONTRAINTES FINALES STRICTES ⚠️
- Ne créez PAS d'analyse ou de résumé des facteurs locaux
- Ne mentionnez PAS l'impact des établissements sur la valeur immobilière
- Copiez UNIQUEMENT et INTÉGRALEMENT les données fournies ci-dessus
- Présentez CHAQUE établissement avec EXACTEMENT le même format et niveau de détail
- Incluez UNIQUEMENT les catégories que le client a sélectionnées: {", ".join(facteurs_selectionnes)}
- Utilisez UNIQUEMENT le format demandé, sans aucune variation
- ASSUREZ-VOUS qu'il y a un espace AVANT et APRÈS les deux points dans les informations (par exemple "À pied : " et non "À pied:")
- ASSUREZ-VOUS qu'il y a un espace après les virgules dans les listes de lignes

Ces informations sont cruciales et doivent être présentées de manière exacte, complète et uniforme.
"""
    
    return local_factors_prompt

# Traitement des facteurs locaux
def process_local_factors(form_data):
    """
    Génère une section du prompt pour les facteurs locaux sélectionnés par l'utilisateur.
    """
    if not form_data.get('localFactors'):
        return ""
    
    # Version améliorée qui utilise l'API Google Maps
    return improved_local_factors_with_google_maps(form_data)
    
    # Ancien code (conservé en commentaire pour référence)
    """
    # Traduction des codes en descriptions
    factor_descriptions = {
        'transport': 'Transports en commun (métro, bus, tram, train)',
        'schools': 'Proximité des écoles et établissements éducatifs',
        'shops': 'Commerces et services de proximité',
        'security': 'Sécurité et tranquillité du quartier',
        'development': 'Projets urbains et développements futurs',
        'employment': 'Bassin d\'emploi et activité économique'
    }
    
    local_factors_prompt = "\n\n### FACTEURS LOCAUX IMPORTANTS\n"
    local_factors_prompt += "Le client accorde une importance particulière aux facteurs suivants. Veuillez les analyser en détail :\n"
    
    for factor in form_data.get('localFactors', []):
        if factor in factor_descriptions:
            local_factors_prompt += f"- {factor_descriptions[factor]}\n"
    
    return local_factors_prompt
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
