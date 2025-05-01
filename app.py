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
    soup = BeautifulSoup(html_content, "html.parser")
    styles = getSampleStyleSheet()  # Récupère les styles par défaut de ReportLab

    # Calcul de la largeur de la page disponible (A4 moins les marges de 2 cm de chaque côté)
    PAGE_WIDTH = A4[0] - 4 * cm

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
            
            # Détermination du nombre de colonnes (on suppose que toutes les lignes ont le même nombre de cellules)
            col_count = len(table_data[0]) if table_data and table_data[0] else 1
            col_width = PAGE_WIDTH / col_count  # Largeur égale pour chaque colonne

            # Ajustement de la taille de la police selon la largeur des colonnes
            font_size = 10
            if col_width < 2 * cm:
                font_size = 8
            title_font_size = 8
            if col_width < 1 * cm:
                title_font_size = 5

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
        elif elem.name:
            # Pour tout autre élément HTML, on crée un Paragraph simple
            paragraph = Paragraph(clean_text(elem.get_text(strip=True)), styles['BodyText'])
            elements.append(paragraph)
            elements.append(Spacer(1, 12))
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

        for section_title, min_words in sections:
            # Générer le prompt de base pour cette section
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

#### **6. Évaluation des risques**
Générez une évaluation complète des risques liés à l'investissement, incluant :
- Une analyse des risques de marché (vacance locative, fluctuations des prix).
- Un tableau illustrant les variations annuelles des prix au m² pour évaluer la stabilité du marché.

---

#### **7. Conclusion et recommandations**
Générez une conclusion complète, incluant :
- Cher(e) client_name = form_data.get('Nom Prénom', 'Client'),En conclusion de notre analyse approfondie, voici un résumé des points clés à retenir pour votre projet d'investissement :	
- Une synthèse des données clés (prix au m², rendement locatif, etc.).
- Une recommandation claire sur l'opportunité d'investir.
- Une évaluation globale de l'opportunité d'investir.
- Les principales tendances observées sur le marché immobilier.
- Des recommandations concrètes adaptées aux objectifs du client.
- Intégrez une recommandation personnalisée indiquant si, d'après les données en temps réel, il serait préférable d'investir dans l'appartement ciblé ou d'envisager une alternative offrant un meilleur rendement locatif.
Ne fournissez aucun tableau dans cette section.

#### **8. Analyse prédictive et argumentée**
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
            
            # Ajout des facteurs locaux au prompt après la section "Analyse du produit"
            if section_title == "Analyse du produit":
                # Générer la section des facteurs locaux
                local_factors_prompt = process_local_factors(form_data)
                if local_factors_prompt:
                    # Ajouter les instructions pour le modèle sur comment traiter ces facteurs
                    local_factors_section = """
                    
#### **Facteurs locaux importants**
Après avoir généré la section "Analyse du produit", continuez avec une analyse détaillée des facteurs locaux suivants qui sont importants pour le client. 

⚠️ ATTENTION - INSTRUCTIONS CRITIQUES ⚠️
Les informations qui suivent sont basées sur des données réelles obtenues via Google Maps et DOIVENT être copiées INTÉGRALEMENT dans votre rapport. 

VOUS DEVEZ ABSOLUMENT:
- Copier SANS MODIFICATION et SANS OMISSION toutes les informations fournies
- Créer une section détaillée avec un titre "Facteurs locaux importants"
- Lister TOUS les établissements avec TOUTES leurs informations:
  * Nom exact (sans changement)
  * Distance et durée à pied ET en voiture (avec les valeurs exactes)
  * Adresse complète de chaque lieu
  * Pour les transports: type exact et TOUS les numéros de lignes
  * Toutes autres informations (note, téléphone, site web)
- Conserver la structure exacte par catégories et sous-catégories
- IMPORTANT: Pour chaque station de transport, copier exactement le type et toutes les lignes indiquées

Il est CRUCIAL que ces données soient reproduites à l'identique. Toutes les distances, durées et autres détails sont des informations FACTUELLES qui doivent apparaître TELLES QUELLES dans le rapport final. Ne résumez pas, ne paraphrasez pas - REPRODUISEZ EXACTEMENT.

Un rapport incomplet ou imprécis est INACCEPTABLE pour le client.
"""
                    section_prompt += local_factors_section + local_factors_prompt
            
            section_content = generate_section(client, section_prompt)
    
            # Si le premier élément est un Paragraph dont le texte correspond exactement au titre, le supprimer
            if section_content and hasattr(section_content[0], "getPlainText"):
                first_text = section_content[0].getPlainText().strip().lower()
                if first_text == section_title.strip().lower():
                    section_content.pop(0)
    
            # Ajout du titre de section dans le document
            add_section_title(elements, section_title)
            elements.extend(section_content)  # Ajoute le contenu de la section sans duplication du titre
            
            # Si c'est la section "Analyse du produit" et qu'il y a des facteurs locaux, ajouter une sous-section
            if section_title == "Analyse du produit" and process_local_factors(form_data):
                # Créer un style pour le sous-titre
                subtitle_style = ParagraphStyle(
                    'SubSectionTitle',
                    fontSize=14,
                    fontName='Helvetica-Bold',
                    textColor=colors.HexColor("#00C7C4"),
                    alignment=0,
                    spaceAfter=8
                )
                # Ajouter un espacement
                elements.append(Spacer(1, 12))
                
                # Ajouter la carte Google Maps si disponible
                if map_path and os.path.exists(map_path):
                    elements.append(Paragraph("Localisation de la propriété", subtitle_style))
                    map_img = Image(map_path, width=450, height=300)
                    elements.append(map_img)
                    elements.append(Spacer(1, 12))
            
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
            'transport': ['bus_station', 'subway_station', 'train_station', 'transit_station', 'light_rail_station', 'tram_station'],
            'security': ['police']
        }
        
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
                nearby_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius=2000&type={place_type}&key={api_key}"
                logging.debug(f"URL nearby search : {nearby_url}")
                nearby_response = requests.get(nearby_url)
                nearby_data = nearby_response.json()
                
                if nearby_data.get('status') == 'OK':
                    logging.info(f"Nombre de résultats pour {place_type}: {len(nearby_data.get('results', []))}")
                    # Stocker les résultats par type de lieu
                    place_results = []
                    for place in nearby_data.get('results', [])[:5]:  # Limiter à 5 résultats maximum par type
                        # Récupérer les détails du lieu pour obtenir plus d'informations
                        place_id = place.get('place_id')
                        
                        # Calculer les distances et temps de trajet à pied seulement (pour réduire la taille)
                        walking_distance, walking_duration = calculate_distance((lat, lng), 
                                                                (place['geometry']['location']['lat'], 
                                                                place['geometry']['location']['lng']), 
                                                                api_key, mode="walking")
                        
                        # Calculer les distances et temps de trajet en voiture
                        driving_distance, driving_duration = calculate_distance((lat, lng), 
                                                                (place['geometry']['location']['lat'], 
                                                                place['geometry']['location']['lng']), 
                                                                api_key, mode="driving")
                        
                        if place_id and place_type in ['bus_station', 'subway_station', 'train_station', 'transit_station', 'light_rail_station', 'tram_station']:
                            try:
                                # Récupération des détails complets pour les stations de transport
                                details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_address,type,rating,formatted_phone_number,website&key={api_key}"
                                details_response = requests.get(details_url)
                                details_data = details_response.json()
                                
                                # Déterminer le type de transport
                                transport_type = "station"
                                if "bus" in place_type or any(t for t in place.get('types', []) if 'bus' in t):
                                    transport_type = "bus"
                                elif "subway" in place_type or any(t for t in place.get('types', []) if 'subway' in t):
                                    transport_type = "métro"
                                elif "tram" in place_type or any(t for t in place.get('types', []) if 'tram' in t):
                                    transport_type = "tram"
                                elif "train" in place_type or any(t for t in place.get('types', []) if 'train' in t):
                                    transport_type = "train"
                                
                                # Extraire les numéros de ligne potentiels du nom
                                name = place['name']
                                lines = []
                                
                                # Tentative d'extraction de numéros/lettres de lignes du nom
                                import re
                                # Recherche de motifs comme "Ligne 1", "Bus 42", "Tram A", etc.
                                line_matches = re.findall(r'(ligne|bus|tram|metro|métro|train|lignes?)\s*([a-z0-9]+)', name.lower())
                                if line_matches:
                                    for match in line_matches:
                                        lines.append(f"{match[1]}")
                                
                                # Si pas de lignes trouvées, vérifier des numéros isolés qui pourraient être des lignes
                                if not lines:
                                    number_matches = re.findall(r'\b[0-9]+\b', name)
                                    if number_matches:
                                        lines = number_matches
                                
                                # Obtenir l'adresse formatée si disponible
                                address_details = details_data.get('result', {}).get('formatted_address', '')
                                
                                # Recherche dans l'adresse pour des indices supplémentaires
                                if address_details:
                                    # Recherche de formats comme "Ligne 1", "Bus 42", etc. dans l'adresse
                                    addr_line_matches = re.findall(r'(ligne|bus|tram|metro|métro|train|lignes?)\s*([a-z0-9]+)', address_details.lower())
                                    for match in addr_line_matches:
                                        if match[1] not in lines:
                                            lines.append(f"{match[1]}")
                                    
                                    # Recherche de numéros isolés dans l'adresse
                                    if not lines:
                                        addr_number_matches = re.findall(r'\b[0-9]+\b', address_details)
                                        for num in addr_number_matches:
                                            if num not in lines and len(num) < 3:  # Limiter aux numéros courts (probablement des lignes)
                                                lines.append(num)
                                
                                # Si aucune ligne n'est trouvée, essayer d'autres méthodes
                                if not lines and transport_type in ["bus", "métro", "tram"]:
                                    if transport_type == "bus":
                                        lines.append("Bus")
                                    elif transport_type == "métro":
                                        lines.append("Métro")
                                    elif transport_type == "tram":
                                        lines.append("Tram")
                                
                                place_info = {
                                    'name': place['name'],
                                    'distance': walking_distance,
                                    'duration': walking_duration,
                                    'driving_distance': driving_distance,
                                    'driving_duration': driving_duration,
                                    'address': address_details,
                                    'transport_type': transport_type,
                                    'lines': lines
                                }
                                
                                # Ajouter d'autres détails si disponibles
                                if 'rating' in details_data.get('result', {}):
                                    place_info['rating'] = details_data['result']['rating']
                                if 'formatted_phone_number' in details_data.get('result', {}):
                                    place_info['phone'] = details_data['result']['formatted_phone_number']
                                if 'website' in details_data.get('result', {}):
                                    place_info['website'] = details_data['result']['website']
                            except Exception as e:
                                logging.error(f"Erreur lors de la récupération des détails: {e}")
                                place_info = {
                                    'name': place['name'],
                                    'distance': walking_distance,
                                    'duration': walking_duration
                                }
                        else:
                            try:
                                # Pour les commerces et écoles, récupérer seulement l'adresse
                                if place_id:
                                    details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_address&key={api_key}"
                                    details_response = requests.get(details_url)
                                    details_data = details_response.json()
                                    
                                    # Obtenir l'adresse formatée si disponible
                                    address_details = details_data.get('result', {}).get('formatted_address', '')
                                    
                                    place_info = {
                                        'name': place['name'],
                                        'distance': walking_distance,
                                        'duration': walking_duration,
                                        'address': address_details
                                    }
                                else:
                                    place_info = {
                                        'name': place['name'],
                                        'distance': walking_distance,
                                        'duration': walking_duration
                                    }
                            except Exception as e:
                                logging.error(f"Erreur lors de la récupération des détails: {e}")
                                place_info = {
                                    'name': place['name'],
                                    'distance': walking_distance,
                                    'duration': walking_duration
                                }
                                
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

def calculate_distance(origin, destination, api_key, mode="walking"):
    """
    Calcule la distance et le temps de trajet entre deux points.
    
    Args:
        origin: Coordonnées d'origine (lat, lng)
        destination: Coordonnées de destination (lat, lng)
        api_key: Clé API Google Maps
        mode: Mode de transport ("walking" ou "driving")
        
    Returns:
        Tuple (distance, duration) avec les valeurs textuelles
    """
    try:
        # URL de l'API Distance Matrix
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin[0]},{origin[1]}&destinations={destination[0]},{destination[1]}&mode={mode}&key={api_key}"
        
        response = requests.get(url)
        data = response.json()
        
        if data.get('status') == 'OK' and data.get('rows', [{}])[0].get('elements', [{}])[0].get('status') == 'OK':
            # Distance et durée
            distance = data['rows'][0]['elements'][0]['distance']['text']
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
            
            # Estimer la durée (vitesse moyenne à pied: 5 km/h, en voiture: 30 km/h)
            speed = 5 if mode == "walking" else 30  # km/h
            duration_hours = (distance / 1000) / speed
            duration_minutes = int(duration_hours * 60)
            
            distance_str = f"{int(distance)} m" if distance < 1000 else f"{distance/1000:.1f} km"
            duration_str = f"{duration_minutes} min"
            
            return distance_str, duration_str
    except Exception as e:
        logging.error(f"Erreur lors du calcul de la distance: {e}")
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
        max_items = 10  # Augmenter le nombre d'éléments pour montrer plus de lieux à proximité
        
        for place_type, places in factor_data.items():
            if places:
                factor_text += f"### **{place_type_names.get(place_type, place_type)}**\n\n"
                
                # Trier les lieux par distance (du plus proche au plus éloigné)
                try:
                    def extract_distance(place):
                        distance_str = place.get('distance', '99999 km')
                        if not isinstance(distance_str, str):
                            return 99999
                        # Extraire juste le nombre, ignorer l'unité
                        try:
                            # Pour les formats comme "700 m" ou "1.5 km"
                            num_str = distance_str.split()[0].replace(',', '.')
                            num = float(num_str)
                            # Convertir les km en m pour comparer correctement
                            if 'km' in distance_str:
                                num = num * 1000
                            return num
                        except:
                            return 99999
                    
                    sorted_places = sorted(places, key=extract_distance)
                except:
                    sorted_places = places  # En cas d'erreur, utiliser la liste non triée
                
                for place in sorted_places:
                    # Vérifier si on a atteint la limite d'éléments par facteur
                    if items_count >= max_items:
                        break
                    
                    # Format structuré sur plusieurs lignes comme demandé dans l'exemple
                    name = place['name']
                    
                    # Pour les transports, ajouter les numéros de lignes au nom
                    if place_type in ['bus_station', 'subway_station', 'train_station', 'transit_station', 'light_rail_station', 'tram_station'] and 'lines' in place and place['lines']:
                        lines_str = ", ".join(place['lines'])
                        factor_text += f"**{name} ({lines_str})**\n"
                    else:
                        factor_text += f"**{name}**\n"
                    
                    # Ajouter la distance et durée à pied sur une ligne séparée
                    if 'distance' in place and 'duration' in place:
                        factor_text += f"À pied : {place['distance']} ({place['duration']})\n"
                    
                    # Ajouter la distance et durée en voiture sur une ligne séparée
                    if 'driving_distance' in place and 'driving_duration' in place:
                        factor_text += f"En voiture : {place['driving_distance']} ({place['driving_duration']})\n"
                    
                    # Type d'établissement sur une ligne séparée
                    if 'transport_type' in place and place['transport_type']:
                        factor_text += f"Type : {place['transport_type']}\n"
                    
                    # Ajouter les numéros de lignes pour les transports sur une ligne séparée
                    if 'lines' in place and place['lines']:
                        lines_str = ", ".join(place['lines'])
                        factor_text += f"Lignes : {lines_str}\n"
                    
                    # Ajouter l'adresse sur une ligne séparée
                    if 'address' in place and place['address']:
                        factor_text += f"Adresse : {place['address']}\n"
                    
                    # Ajouter la note si disponible
                    if 'rating' in place:
                        factor_text += f"Note : {place['rating']}/5\n"
                    
                    # Ajouter le numéro de téléphone si disponible
                    if 'phone' in place:
                        factor_text += f"Téléphone : {place['phone']}\n"
                    
                    # Ajouter le site web si disponible
                    if 'website' in place:
                        factor_text += f"Site web : {place['website']}\n"
                    
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
    
    # Créer le prompt avec les données réelles
    local_factors_prompt = f"""

# **FACTEURS LOCAUX IMPORTANTS**
Le client accorde une importance particulière aux facteurs suivants pour l'adresse {address}, {city}. Voici les données précises obtenues:

{formatted_google_data}

**INSTRUCTIONS IMPÉRATIVES:**
1. Vous DEVEZ COPIER INTÉGRALEMENT toutes les informations ci-dessus dans votre rapport, en gardant exactement la même structure et mise en forme.
2. N'OMETTEZ AUCUN détail - toutes les distances, durées, adresses et autres informations sont ESSENTIELLES.
3. Pour CHAQUE ÉTABLISSEMENT listé, incluez:
   - Son nom exact
   - La distance et durée à pied
   - Le type précis (bus/métro/tram/train)
   - TOUS les numéros de lignes lorsqu'ils sont disponibles
   - L'adresse complète
4. Conservez impérativement la mise en forme des titres et sous-titres en gras.
5. Gardez la structure exacte avec chaque établissement sur plusieurs lignes comme présenté.
6. Les informations proviennent de Google Maps et sont 100% précises et vérifiées - ne les modifiez pas.
7. Si certaines informations sont manquantes pour certains établissements, ne les inventez pas.
8. Ces données sont l'élément le plus crucial du rapport - leur présence complète et fidèle est OBLIGATOIRE.

Ces informations sont cruciales pour évaluer la qualité de vie dans le quartier et l'attractivité du bien pour d'éventuels locataires.
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
