from flask import Flask, request, send_file, jsonify, url_for
from openai import OpenAI
import os
import logging
import ssl
import unicodedata
import re
from flask_cors import CORS
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from PIL import Image as PILImage
from datetime import datetime
import tempfile
import requests
from markdown import markdown
from io import StringIO

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
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return f"Key loaded successfully: {api_key[:6]}...hidden", 200
    return "API key not found", 500

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

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
from reportlab.lib.pagesizes import A4

def markdown_to_elements(md_text):
    elements = []
    # Conversion du Markdown en HTML avec support des tableaux
    html_content = md_to_html(md_text, extras=["tables"])
    
    # Correction des problèmes d'espaces entre les noms et les informations "À pied"
    # Remplacer les occurrences problématiques comme "NomÀ pied" par "Nom À pied"
    html_content = re.sub(r'(\w+)À pied', r'\1 À pied', html_content)
    
    soup = BeautifulSoup(html_content, "html.parser")
    styles = getSampleStyleSheet()  # Récupère les styles par défaut de ReportLab
    
    # Créer des styles personnalisés pour la mise en page des facteurs locaux
    bold_style = ParagraphStyle(
        'Bold',
        parent=styles['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=11,
        spaceAfter=6,
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        spaceAfter=2,
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.HexColor("#00C7C4"),
        spaceAfter=8,
        spaceBefore=6,
    )
    
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=colors.HexColor("#00C7C4"),
        spaceAfter=10,
        spaceBefore=12,
    )

    # Calcul de la largeur de la page disponible (A4 moins les marges de 2 cm de chaque côté)
    PAGE_WIDTH = A4[0] - 4 * cm

    # Traitement spécial pour les facteurs locaux
    is_local_factors = False
    current_element_type = None
    
    for elem in soup.contents:
        if elem.name == "table":
            table_data = []
            for row in elem.find_all("tr"):
                row_data = []
                for cell in row.find_all(["td", "th"]):
                    # Récupération du texte de la cellule
                    cell_text = cell.get_text(strip=True)
                    # Création d'un Paragraph pour activer le wrapping
                    para = Paragraph(cell_text, styles['BodyText'])
                    row_data.append(para)
                table_data.append(row_data)
            
            # Détermination du nombre de colonnes
            col_count = len(table_data[0]) if table_data and table_data[0] else 1
            col_width = PAGE_WIDTH / col_count  # Largeur égale pour chaque colonne

            # Ajustement de la taille de la police selon la largeur des colonnes
            font_size = 10
            if col_width < 2 * cm:
                font_size = 8
            title_font_size = 8
            if col_width < 1 * cm:
                title_font_size = 6

            # Définition du style du tableau
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), font_size),
                ('FONTSIZE', (0, 1), (-1, -1), font_size - 2),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ])

            table = Table(table_data, colWidths=[col_width] * col_count, style=table_style)
            elements.append(table)
            elements.append(Spacer(1, 6))  # Espace réduit après le tableau
            
        elif elem.name == "h2":  # Titres principaux (## dans markdown)
            # Vérifier si on entre dans la section des facteurs locaux
            if "facteurs locaux" in elem.get_text().lower():
                is_local_factors = True
            
            # Traiter le titre
            text = clean_text(elem.get_text(strip=True))
            elements.append(Paragraph(text, title_style))
            elements.append(Spacer(1, 6))
            current_element_type = "title"
            
        elif elem.name == "h3":  # Sous-titres (### dans markdown)
            text = clean_text(elem.get_text(strip=True))
            elements.append(Paragraph(text, subtitle_style))
            elements.append(Spacer(1, 4))
            current_element_type = "subtitle"
            
        elif elem.name == "p":  # Paragraphes
            text = clean_text(elem.get_text(strip=True))
            
            # Traitement spécial pour les facteurs locaux
            if is_local_factors:
                # Vérifier s'il s'agit d'un élément en gras (nom d'établissement)
                if elem.find("strong") or elem.find("b"):
                    elements.append(Paragraph(text, bold_style))
                    current_element_type = "place_name"
                # Vérifier s'il s'agit d'une ligne d'information
                elif any(info in text.lower() for info in ["à pied", "en voiture", "type", "lignes", "adresse", "note", "téléphone", "site web"]):
                    # Ajouter un peu d'indentation pour mieux distinguer ces informations
                    indented_text = "&nbsp;&nbsp;&nbsp;" + text
                    elements.append(Paragraph(indented_text, normal_style))
                    current_element_type = "place_info"
                else:
                    elements.append(Paragraph(text, styles['BodyText']))
                    elements.append(Spacer(1, 6))
                    current_element_type = "paragraph"
            else:
                # Traitement normal pour les autres sections
                elements.append(Paragraph(text, styles['BodyText']))
                elements.append(Spacer(1, 12))
                current_element_type = "paragraph"
                
        elif elem.name == "hr":  # Ligne horizontale (---)
            # Ajouter un séparateur visuel
            elements.append(Spacer(1, 4))
            elements.append(Paragraph("<hr/>", normal_style))
            elements.append(Spacer(1, 4))
            
        elif elem.name:  # Pour tout autre élément HTML
            text = clean_text(elem.get_text(strip=True))
            if text.strip():  # Ignorer les éléments vides
                elements.append(Paragraph(text, styles['BodyText']))
                elements.append(Spacer(1, 8))
    
    return elements

def add_section_title(elements, title):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'SectionTitle',
        fontSize=16,
        fontName='Helvetica',
        textColor=colors.HexColor("#00C7C4"),
        alignment=1,
        spaceAfter=12,
        underline=True
    )
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 12))

def generate_section(client, section_prompt, max_tokens=1700):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Vous êtes un expert de renommée mondiale en analyse financière et immobilière, spécialisé dans l'immobilier résidentiel et commercial. En tant qu'expert, votre tâche est de générer un rapport détaillé et professionnel intégrant des données chiffrées comme le prix moyen au mètre carré, l'évolution des prix sur plusieurs années ou encore le rendement locatif. Fournissez des analyses spécifiques comme l'impact des établissements scolaires, la qualité des infrastructures disponibles, et tout autre élément pertinent. Incluez des tableaux et graphiques pour une représentation visuelle des données ainsi que des recommandations de quartiers adaptées aux critères du client et aux objectifs qu'il souhaite atteindre. Analysez les tendances du marché et prévoyez les évolutions à moyen et long terme. Le rapport devra être rigoureusement adapté aux critères spécifiques du client et aux caractéristiques locales de la ville ou du bien mentionné tout en adoptant un style clair, précis et professionnel démontrant une parfaite maîtrise des enjeux économiques et sectoriels."},
            {"role": "user", "content": section_prompt}
        ],
        max_tokens=max_tokens,
        temperature=0.7,
        top_p=1,
        frequency_penalty=0.3,  
        presence_penalty=0.3,
    )
    return markdown_to_elements(response.choices[0].message.content)

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

        # Récupérer la langue choisie dans le formulaire (valeurs attendues : 'fr', 'en', 'es', 'de', 'ru', 'pt', 'zh', 'nl', 'ja', 'ar')
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

        sections = [
            ("Introduction", 200),
            ("Contexte", 250),
            ("Secteur d'investissement", 400),
            ("Analyse du marché", 500),
            ("Analyse du produit", 500),
            ("Facteurs locaux importants", 500),  # Ajout d'une section dédiée aux facteurs locaux
            ("Évaluation des risques", 450),
            ("Conclusion et recommandations", 500),
            ("Analyse prédictive et argumentée", 500)
        ]

        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_{name.replace(' ', '_')}.pdf")
        doc = SimpleDocTemplate(pdf_filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)

        elements = []
        styles = getSampleStyleSheet()

        cover_images = [
            "static/cover_image.png",
            "static/cover_image1.png",
        ]

        resized_images = []
        for i, image_name in enumerate(cover_images):
            image_path = os.path.join(os.path.dirname(__file__), image_name)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                output_path = temp_file.name
                resize_image(image_path, output_path)
                resized_images.append(output_path)

        for image_path in resized_images:
            elements.append(Image(image_path, width=469, height=716))
            elements.append(PageBreak())

        add_section_title(elements, "Informations du Client")
        client_info_data = [
            ["Nom", name],
            ["Date de l'Analyse", analysis_date],
            ["Secteur d'Investissement", investment_sector],
            ["Adresse", address],
            ["Email", email],
            ["Téléphone", phone]
        ]
        t = Table(client_info_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#00C7C4")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 14),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige),
            ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 12),
            ('TOPPADDING', (0,1), (-1,-1), 6),
            ('BOTTOMPADDING', (0,1), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 12))

        # Générer une carte statique de l'adresse
        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyAqcyOXDwvgVW4eYy5vqW8TXM5FQ3DKB9w")
        map_path = get_google_static_map(address, city, api_key)
        # Générer une image Street View de l'immeuble ou de la rue
        street_view_path = get_street_view_image(address, city, api_key)

        for section_title, min_words in sections:
            # Si nous traitons la section des facteurs locaux, nous gérons différemment
            if section_title == "Facteurs locaux importants":
                if process_local_factors(form_data):
                    # Ajouter le titre pour la section des facteurs locaux
                    add_section_title(elements, "Facteurs locaux importants")
                    
                    # Créer un style pour le sous-titre
                    subtitle_style = ParagraphStyle(
                        'SubSectionTitle',
                        fontSize=14,
                        fontName='Helvetica-Bold',
                        textColor=colors.HexColor("#00C7C4"),
                        alignment=0,
                        spaceAfter=8
                    )
                    
                    # Ajouter la carte Google Maps en premier si disponible
                    if map_path and os.path.exists(map_path):
                        elements.append(Paragraph("Localisation de la propriété", subtitle_style))
                        map_img = Image(map_path, width=450, height=300)
                        elements.append(map_img)
                        elements.append(Spacer(1, 10))
                    
                    # Ajouter l'image Street View après la carte si disponible
                    if street_view_path and os.path.exists(street_view_path):
                        elements.append(Paragraph("Vue de l'immeuble", subtitle_style))
                        sv_img = Image(street_view_path, width=450, height=300)
                        elements.append(sv_img)
                        elements.append(Spacer(1, 20))
                    
                    # Générer le contenu des facteurs locaux
                    local_factors_prompt = process_local_factors(form_data)
                    local_factors_content = generate_section(client, local_factors_prompt, max_tokens=3500)
                    
                    # Ajouter le contenu des facteurs locaux (sans ajouter à nouveau le titre)
                    for elem in local_factors_content:
                        if hasattr(elem, 'getPlainText') and section_title.lower() in elem.getPlainText().lower():
                            # Ignorer l'élément si c'est le titre principal qui se répète
                            continue
                        elements.append(elem)
                    
                    elements.append(PageBreak())
                    continue  # Passer à la section suivante
            
            # Pour les autres sections normales
            section_prompt = f"""
            {summary}

            {market_data_str}
La langue du rapport doit être : {language_name}.

Votre tâche est de générer la section '{section_title}' du rapport d'analyse immobilier, en fournissant des informations de qualité professionnelle adaptées et choisie par le client. Suivez scrupuleusement les consignes suivantes :

---

### Instructions Générales

1. **Structure et Clarté** :
   - Ne répétez pas les informations des autres sections.
   - Évitez les sous-menus ou sous-sections supplémentaires.

2. **Utilisation des Tableaux** :
   - Tous les tableaux doivent être générés dynamiquement par OpenAI en fonction des données du formulaire client.
   - Les tableaux doivent être insérés tels qu'ils sont générés, au format Markdown.
   - Ne reconstruisez pas les tableaux ou leur format.
   - Assurez-vous que chaque tableau soit unique à la section et suivi d'une description claire expliquant son contenu et sa pertinence.

3. **Organisation des Sections** :
   - **Introduction** : Vue d'ensemble des objectifs d'investissement et aperçu rapide du marché local.
   - **Contexte** : Analyse historique et démographique détaillée de la ville, incluant des données sur la population, les infrastructures et le développement économique.
   - **Secteur d'investissement** : Inclure l'évolution des prix au m² (5 dernières années) et le rendement locatif moyen (2020-2025) pour la ville {address}.
   - **Analyse du marché** : Inclure l'évolution des prix immobiliers (2020-2025), un tableau comparatif des quartiers dans la ville (prix au m², rendement locatif, distances), et les facteurs influençant le marché local.
   - **Analyse du produit** : Évaluation des caractéristiques spécifiques du produit immobilier ciblé.
   - **Facteurs locaux importants** : Détails sur les commerces, écoles, transports et autres services à proximité.
   - **Évaluation des risques** : Analyse des risques liés à l'investissement dans la ville.
   - **Conclusion et recommandations** : Synthèse des données clés et recommandations claires pour le client.
   - **Analyse prédictive et argumentée** : Projection sur l'évolution future des prix immobiliers pour les 5 à 10 prochaines années, analyse argumentée sur le type de bien le plus judicieux à acquérir, et recommandations basées sur les tendances du marché et données économiques.

4. **Détails à Inclure** :
   - Donnez un ou deux aperçus précis des infrastructures, des quartiers importants et des facteurs économiques spécifiques à la ville.
   - Ajoutez des données pertinentes sur la population, la demande locative et les tendances démographiques.
   - Fournissez des insights basés sur des chiffres, comme "le prix moyen au m² est de ...", et comparez plusieurs quartiers.
   - Ajoutez au moins une projection à moyen terme pour les prix immobiliers dans la ville.
   - Intégrez une recommandation personnalisée indiquant si, d'après les données en temps réel, il serait préférable d'investir dans l'appartement ciblé ou d'envisager une alternative offrant un meilleur rendement locatif.

   **Exemple attendu pour les tableaux générés dynamiquement** :
   - **Secteur d'investissement** : Tableau de l'évolution des prix au m² sur 5 ans et du rendement locatif moyen.
   - **Analyse du marché** : Tableau comparatif des quartiers dans la ville choisie avec des colonnes adaptées aux données locales (prix, rendement locatif, distances, etc.).

2. **Tableaux au format Markdown** :
   - Tous les tableaux doivent être générés en Markdown, avec une première ligne contenant les en-têtes (séparés par |) et une deuxième ligne définissant les séparateurs avec "---".
   - Voici un exemple de format attendu :
   ```markdown
   | Année | Prix Moyen au m² (€) |
   |-------|-----------------------|
   | 2020  | 4,200                |
   | 2021  | 4,350                |
---

### Instructions par Section

#### **1. Introduction**
Générez une introduction qui inclut :
- Cher(e) client_name = form_data.get('Nom Prénom', 'Client'),Ce rapport a été préparé spécifiquement pour votre projet d'investissement. Notre analyse vise à vous fournir une vue d'ensemble claire et détaillée du marché immobilier local pertinent pour votre objectif.
- Une présentation des objectifs d'investissement du formulaire client (exemple : investir dans un appartement de 120m² pour un usage locatif).
- Une explication rapide de l'importance du marché local pour cet investissement.
- Aucun tableau dans cette section.

---

#### **2. Contexte**
Générez une analyse détaillée du contexte local, incluant :
- Une présentation générale de la ville : population, attractivité économique, infrastructures clés.
- Une analyse des tendances immobilières et démographiques sur les 5 dernières années.
- Aucun tableau dans cette section, uniquement des informations textuelles détaillées.

---

#### **3. Secteur d'investissement**
Générez une analyse détaillée du secteur d'investissement, incluant :
- Un tableau dynamique montrant l'évolution des prix moyens au m² dans la ville sur les 5 dernières années.
- Un tableau dynamique illustrant le rendement locatif moyen de la ville pour la période 2020-2025.
- Une description claire expliquant les tendances et leur pertinence pour l'investissement.

---

#### **4. Analyse du marché**
Générez une analyse approfondie du marché immobilier local, incluant :
- Un tableau dynamique montrant l'évolution des prix immobiliers de la ville sur la période 2020-2025.
- Un tableau dynamique montrant l'évolution des prix immobiliers dans les villes voisines sur la période 2020-2025.
- Un tableau comparatif dynamique entre différents quartiers, avec les colonnes suivantes :
  - Prix moyen au m².
  - Rendement locatif (%).
  - Distances moyennes aux commerces et écoles.
- Une analyse expliquant les facteurs influençant les prix et les rendements locatifs.

---

#### **5. Analyse du produit**
Générez une analyse détaillée du produit immobilier ciblé par le client, incluant :
- Une description des caractéristiques de l'appartement cible (taille, emplacement, infrastructures à proximité).
- Un tableau dynamique montrant l'évolution des prix immobiliers des villes voisines sur la période 2020-2025.
- Un tableau montrant les prix moyens au m² pour des biens similaires dans le quartier ciblé.
- Le type de bien (par exemple, Appartement Neuf, Appartement Ancien, Maison Individuelle).
- La superficie (exemple : 120 m²).
- Le prix moyen au m² pour chaque type de bien.

Le tableau doit être clair et au format Markdown. Fournissez également une description concise sous le tableau expliquant les différences de prix entre les biens.

| Type de bien                | Superficie (m²) | Prix moyen au m² (€) |
|-----------------------------|-----------------|-----------------------|
| Centre Ville Appartement Neuf  | 120             | 8,500                |
| Centre Ville Appartement Ancien| 120             | 7,000                |
| Centre Ville Maison Individuelle| 120            | 9,000                |

Description : Ce tableau compare les prix moyens pour différents types de biens immobiliers dans le quartier cible, afin d'évaluer leur compétitivité sur le marché local.
---

#### **6. Facteurs locaux importants**
Générez une analyse des facteurs locaux importants pour le bien immobilier, incluant :
- Une présentation des points d'intérêt et services à proximité : commerces, écoles, transports, etc.
- Pour chaque établissement mentionné, incluez des distances précises, des durées de trajet et des informations de contact lorsque disponibles.
- Ces informations doivent être organisées de manière claire et hiérarchisée.

---

#### **7. Évaluation des risques**
Générez une évaluation complète des risques liés à l'investissement, incluant :
- Une analyse des risques de marché (vacance locative, fluctuations des prix).
- Un tableau illustrant les variations annuelles des prix au m² pour évaluer la stabilité du marché.

---

#### **8. Conclusion et recommandations**
Générez une conclusion complète, incluant :
- Cher(e) client_name = form_data.get('Nom Prénom', 'Client'),En conclusion de notre analyse approfondie, voici un résumé des points clés à retenir pour votre projet d'investissement :	
- Une synthèse des données clés (prix au m², rendement locatif, etc.).
- Une recommandation claire sur l'opportunité d'investir.
- Une évaluation globale de l'opportunité d'investir.
- Les principales tendances observées sur le marché immobilier.
- Des recommandations concrètes adaptées aux objectifs du client.
- Intégrez une recommandation personnalisée indiquant si, d'après les données en temps réel, il serait préférable d'investir dans l'appartement ciblé ou d'envisager une alternative offrant un meilleur rendement locatif.
Ne fournissez aucun tableau dans cette section.

#### **9. Analyse prédictive et argumentée**
Générez une analyse prédictive sur l'évolution future du marché immobilier, incluant :
- Une projection sur l'évolution des prix immobiliers avec des chiffres et des pourcentages pour les 5 à 10 prochaines années.
- Une analyse argumentée sur le type de bien (par exemple, appartement, maison, etc.) le plus judicieux à acquérir pour un investissement.
- Des recommandations basées sur les tendances du marché, les données économiques et démographiques avec un tableau.
- Une conclusion synthétique avec des arguments solides pour soutenir la recommandation.
- Une étude argumentée sur quel type de bien il est plus judicieux d'acquérir dans le secteur choisi par le client pour faire un investissement locatif en tenant compte de la clientèle locative de ce secteur.
- Une analyse argumentée détaillée sur le type de bien le plus judicieux à acquérir pour un investissement. Comparez par exemple un appartement neuf, un appartement ancien et une maison individuelle, en indiquant pour chacun :
   - Le taux de rendement moyen,
   - Les coûts d'acquisition et d'entretien,
   - Le potentiel de valorisation,
   - La demande locative et les tendances démographiques.
- Des recommandations chiffrées basées sur les tendances du marché et des données économiques.
- Une conclusion synthétique avec des arguments solides pour soutenir la recommandation.
---

### Règles Générales

1. **Dynamisme des Données** : Toutes les données, y compris les tableaux, doivent être générées dynamiquement en fonction de la ville choisie {address}.
2. **Respect des Formats** : Les tableaux doivent être insérés exactement tels qu'ils sont générés par OpenAI. Aucun tableau fixe ou reconstruit.
3. **Descriptions Sous les Tableaux** : Chaque tableau doit être suivi d'une description expliquant son contenu et son importance.
4. **Longueur Minimale** : Fournissez un contenu détaillé avec un minimum de {min_words} mots par section.

Pour la section '{section_title}', concentrez-vous uniquement sur les éléments spécifiques à cette section. Ne répétez pas les informations des autres sections ou des parties déjà couvertes ailleurs. Si la section nécessite des comparaisons (comme pour l'analyse du marché), incluez plusieurs perspectives (par exemple, entre quartiers ou types de biens).

            Générez la section '{section_title}' du rapport d'analyse. 
            Cette section doit contenir au minimum {min_words} mots.
            """
            
            # Vérification pour éviter d'ajouter les instructions pour les facteurs locaux après Analyse du produit
            if section_title == "Analyse du produit":
                # Ne rien ajouter ici, car les facteurs locaux sont maintenant une section séparée
                pass
            
            # Générer et ajouter le contenu de la section
            section_content = generate_section(client, section_prompt)
    
            # Si le premier élément est un Paragraph dont le texte correspond exactement au titre, le supprimer
            if section_content and hasattr(section_content[0], "getPlainText"):
                first_text = section_content[0].getPlainText().strip().lower()
                if first_text == section_title.strip().lower():
                    section_content.pop(0)
    
            # Ajout du titre de section dans le document
            add_section_title(elements, section_title)
            elements.extend(section_content)  # Ajoute le contenu de la section sans duplication du titre
            elements.append(PageBreak())

        doc.build(elements)
        logging.info(f"Rapport généré avec succès : {pdf_filename}")
        log_to_file(f"Rapport généré avec succès : {pdf_filename}")

        return send_file(pdf_filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Erreur lors de la génération du rapport : {str(e)}")
        return jsonify({"error": str(e)}), 500

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
