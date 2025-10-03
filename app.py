# Version restaurée le 13/05/2024
# La fonction generate_default_qcm a été modifiée pour générer 10 questions par module et 30 pour le QCM final
from flask import Flask, request, send_file, jsonify, url_for, render_template, redirect
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
import json

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

def generate_section(client, section_prompt, max_tokens=2000):
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
Après avoir généré la section "Analyse du produit", continuez avec une analyse détaillée des facteurs locaux suivants qui sont importants pour le client. Pour chaque facteur listé, fournissez :
- Une analyse détaillée de la situation actuelle
- L'impact potentiel sur la valeur de l'investissement
- Une évaluation comparative par rapport aux autres zones de la ville
- Des données chiffrées si elles sont pertinentes (distances, nombre d'établissements, fréquence des transports, etc.)
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
                    fontName='Helvetica',
                    textColor=colors.HexColor("#00C7C4"),
                    alignment=0,
                    spaceAfter=8
                )
                # Ajouter un espacement
                elements.append(Spacer(1, 12))
            
            elements.append(PageBreak())

        doc.build(elements)
        logging.info(f"Rapport généré avec succès : {pdf_filename}")
        log_to_file(f"Rapport généré avec succès : {pdf_filename}")

        return send_file(pdf_filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Erreur lors de la génération du rapport : {str(e)}")
        return jsonify({"error": str(e)}), 500

# Traitement des facteurs locaux
def process_local_factors(form_data):
    """
    Génère une section du prompt pour les facteurs locaux sélectionnés par l'utilisateur.
    """
    if not form_data.get('localFactors'):
        return ""
    
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

def generate_default_qcm(module_title, module_content="", is_final_quiz=False):
    """
    Génère un QCM adapté au contenu de la formation choisi par le client.
    Utilise le contenu du module pour générer des questions pertinentes.
    Pour le QCM final, génère 30 questions plus difficiles.
    """
    module_title_lower = module_title.lower()
    questions = []
    
    # Nombre de questions à générer
    num_questions = 30 if is_final_quiz else 10
    
    # Questions génériques pour tous les modules
    generic_questions = [
        {
            "question": f"Question 1 sur {module_title}",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 0
        },
        {
            "question": f"Question 2 sur {module_title}",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 1
        },
        {
            "question": f"Question 3 sur {module_title}",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": 2
        }
    ]
    
    # Générer les questions nécessaires
    while len(questions) < num_questions:
        # Ajouter des questions génériques en boucle
        idx = len(questions) % len(generic_questions)
        question = dict(generic_questions[idx])
        question["question"] = f"Question {len(questions)+1} sur {module_title}"
        questions.append(question)
    
    # Limiter au nombre exact de questions requis
    questions = questions[:num_questions]
    
    # Générer le HTML du QCM
    html = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QCM - {module_title}</title>
    <style>
        body {{ font-family: 'Arial', sans-serif; margin: 0; padding: 20px; }}
        .qcm-container {{ max-width: 800px; margin: 0 auto; }}
        .question {{ background-color: #f5f0ff; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="qcm-container">
        <h1>{"QCM Final - Évaluation Complète" if is_final_quiz else f"QCM - {module_title}"}</h1>
        <p>Ce QCM contient {num_questions} questions.</p>
        
        <div class="questions">
            {"".join([f'''
            <div class="question" id="q{i+1}">
                <h3>Question {i+1}</h3>
                <p>{q["question"]}</p>
                <form>
                    {"".join([f'<div><input type="radio" name="q{i+1}" value="{j}"> {option}</div>' for j, option in enumerate(q["options"])])}
                </form>
            </div>
            ''' for i, q in enumerate(questions)])}
        </div>
    </div>
</body>
</html>
"""
    
    return html

@app.route('/rapports', methods=['GET'])
def rapports_page():
    """Page pour générer des rapports immobiliers avec Google Maps et questionnaire"""
    return render_template('rapports.html')

@app.route('/api/geocode', methods=['POST'])
def geocode_address():
    """API pour obtenir les coordonnées GPS d'une adresse"""
    try:
        data = request.json
        address = data.get('address', '')
        if not address:
            return jsonify({"error": "Adresse non fournie"}), 400
            
        # Utiliser l'API de géocodage de Google Maps
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return jsonify({"error": "Clé API Google Maps non configurée"}), 500
            
        response = requests.get(
            f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
        )
        
        result = response.json()
        if result['status'] == 'OK':
            location = result['results'][0]['geometry']['location']
            return jsonify({
                "lat": location['lat'],
                "lng": location['lng'],
                "formatted_address": result['results'][0]['formatted_address']
            })
        else:
            return jsonify({"error": f"Erreur de géocodage: {result['status']}"}), 400
    except Exception as e:
        logging.error(f"Erreur lors du géocodage: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/places', methods=['POST'])
def get_nearby_places():
    """API pour obtenir les lieux à proximité (écoles, commerces, transports)"""
    try:
        data = request.json
        lat = data.get('lat')
        lng = data.get('lng')
        place_type = data.get('type')  # 'school', 'store', 'transit_station'
        
        if not all([lat, lng, place_type]):
            return jsonify({"error": "Paramètres manquants"}), 400
            
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return jsonify({"error": "Clé API Google Maps non configurée"}), 500
            
        response = requests.get(
            f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lng}&radius=1500&type={place_type}&key={api_key}"
        )
        
        result = response.json()
        if result['status'] == 'OK':
            places = []
            for place in result['results'][:10]:  # Limiter aux 10 premiers résultats
                places.append({
                    "name": place.get('name', 'Sans nom'),
                    "vicinity": place.get('vicinity', 'Adresse inconnue'),
                    "lat": place['geometry']['location']['lat'],
                    "lng": place['geometry']['location']['lng'],
                    "rating": place.get('rating', 'Non évalué'),
                    "types": place.get('types', [])
                })
            return jsonify({"places": places})
        else:
            return jsonify({"error": f"Erreur de recherche de lieux: {result['status']}"}), 400
    except Exception as e:
        logging.error(f"Erreur lors de la recherche de lieux: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/streetview', methods=['POST'])
def get_streetview():
    """API pour obtenir l'image Street View d'une adresse"""
    try:
        data = request.json
        lat = data.get('lat')
        lng = data.get('lng')
        
        if not all([lat, lng]):
            return jsonify({"error": "Coordonnées manquantes"}), 400
            
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return jsonify({"error": "Clé API Google Maps non configurée"}), 500
            
        # Construire l'URL de l'image Street View
        streetview_url = f"https://maps.googleapis.com/maps/api/streetview?size=600x400&location={lat},{lng}&key={api_key}"
            
        return jsonify({"streetview_url": streetview_url})
    except Exception as e:
        logging.error(f"Erreur lors de la récupération de Street View: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/save_property', methods=['POST'])
def save_property():
    """API pour sauvegarder les informations d'un bien immobilier"""
    try:
        property_data = request.json
        
        # Créer le dossier de stockage s'il n'existe pas
        properties_dir = os.path.join(os.path.dirname(__file__), 'properties')
        os.makedirs(properties_dir, exist_ok=True)
        
        # Générer un ID unique pour le bien
        property_id = datetime.now().strftime("%Y%m%d%H%M%S")
        property_data['id'] = property_id
        
        # Sauvegarder les données dans un fichier JSON
        file_path = os.path.join(properties_dir, f"property_{property_id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(property_data, f, ensure_ascii=False, indent=4)
        
        return jsonify({"success": True, "property_id": property_id})
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde du bien: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/properties', methods=['GET'])
def get_properties():
    """API pour récupérer la liste des biens immobiliers enregistrés"""
    try:
        properties_dir = os.path.join(os.path.dirname(__file__), 'properties')
        
        if not os.path.exists(properties_dir):
            return jsonify({"properties": []})
        
        properties = []
        for filename in os.listdir(properties_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(properties_dir, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    property_data = json.load(f)
                    properties.append(property_data)
        
        return jsonify({"properties": properties})
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des biens: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete_property/<property_id>', methods=['DELETE'])
def delete_property(property_id):
    """API pour supprimer un bien immobilier"""
    try:
        properties_dir = os.path.join(os.path.dirname(__file__), 'properties')
        file_path = os.path.join(properties_dir, f"property_{property_id}.json")
        
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Bien non trouvé"}), 404
    except Exception as e:
        logging.error(f"Erreur lors de la suppression du bien: {str(e)}")
        return jsonify({"error": str(e)}), 500

def generate_property_report(property_id):
    """Générer un rapport PDF pour un bien immobilier spécifique"""
    try:
        properties_dir = os.path.join(os.path.dirname(__file__), 'properties')
        file_path = os.path.join(properties_dir, f"property_{property_id}.json")
        
        if not os.path.exists(file_path):
            return None, "Bien non trouvé"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            property_data = json.load(f)
        
        # Créer le dossier pour les rapports s'il n'existe pas
        reports_dir = os.path.join(os.path.dirname(__file__), 'property_reports')
        os.makedirs(reports_dir, exist_ok=True)
        
        # Générer le nom du fichier PDF
        property_address = property_data.get('address', 'sans-adresse')
        safe_address = re.sub(r'[^\w\s-]', '', property_address).replace(' ', '_')
        pdf_filename = os.path.join(reports_dir, f"rapport_{safe_address}_{property_id}.pdf")
        
        # Générer le rapport PDF avec les informations du bien
        doc = SimpleDocTemplate(pdf_filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Ajouter un titre au rapport
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Title'],
            fontSize=24,
            textColor=colors.HexColor("#00C7C4"),
            alignment=1,
            spaceAfter=12
        )
        
        elements.append(Paragraph(f"Rapport Immobilier", title_style))
        elements.append(Paragraph(f"{property_address}", styles['Heading1']))
        elements.append(Spacer(1, 20))
        
        # Ajouter les informations du bien
        elements.append(Paragraph("Informations du bien", styles['Heading2']))
        
        # Créer une table pour les informations du bien
        property_info = [
            ["Adresse", property_data.get('address', 'Non spécifiée')],
            ["Type de bien", property_data.get('propertyType', 'Non spécifié')],
            ["Surface", f"{property_data.get('surface', 'Non spécifiée')} m²"],
            ["Prix", f"{property_data.get('price', 'Non spécifié')} €"],
            ["Nombre de pièces", property_data.get('rooms', 'Non spécifié')],
            ["Étage", property_data.get('floor', 'Non spécifié')],
            ["Année de construction", property_data.get('yearBuilt', 'Non spécifiée')]
        ]
        
        t = Table(property_info, colWidths=[150, 300])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#00C7C4")),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(t)
        elements.append(Spacer(1, 20))
        
        # Ajouter la section pour Google Maps
        if property_data.get('lat') and property_data.get('lng'):
            elements.append(Paragraph("Localisation", styles['Heading2']))
            
            # Ajouter l'image Street View si disponible
            if property_data.get('streetview_url'):
                try:
                    response = requests.get(property_data.get('streetview_url'))
                    if response.status_code == 200:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                            temp_file.write(response.content)
                            streetview_path = temp_file.name
                        
                        elements.append(Paragraph("Vue de rue", styles['Heading3']))
                        elements.append(Image(streetview_path, width=400, height=267))
                        elements.append(Spacer(1, 10))
                except Exception as e:
                    logging.error(f"Erreur lors de la récupération de l'image Street View: {str(e)}")
        
        # Ajouter les informations sur les établissements à proximité
        if property_data.get('nearby_places'):
            elements.append(Paragraph("Établissements à proximité", styles['Heading2']))
            
            categories = {
                'school': "Écoles et établissements scolaires",
                'store': "Commerces",
                'transit_station': "Transports en commun"
            }
            
            for place_type, places in property_data.get('nearby_places', {}).items():
                if places:
                    elements.append(Paragraph(categories.get(place_type, place_type), styles['Heading3']))
                    
                    # Créer une table pour les lieux
                    places_data = [["Nom", "Adresse", "Note"]]
                    for place in places:
                        places_data.append([
                            place.get('name', 'Sans nom'),
                            place.get('vicinity', 'Adresse inconnue'),
                            str(place.get('rating', 'Non évalué'))
                        ])
                    
                    t = Table(places_data, colWidths=[200, 200, 50])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#00C7C4")),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 10),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    
                    elements.append(t)
                    elements.append(Spacer(1, 10))
        
        # Ajouter les notes et commentaires
        if property_data.get('notes'):
            elements.append(Paragraph("Notes et commentaires", styles['Heading2']))
            elements.append(Paragraph(property_data.get('notes', ''), styles['BodyText']))
        
        # Générer le PDF
        doc.build(elements)
        
        return pdf_filename, None
    except Exception as e:
        logging.error(f"Erreur lors de la génération du rapport: {str(e)}")
        return None, str(e)

@app.route('/api/generate_report/<property_id>', methods=['GET'])
def api_generate_property_report(property_id):
    """API pour générer un rapport PDF pour un bien immobilier"""
    pdf_path, error = generate_property_report(property_id)
    
    if error:
        return jsonify({"error": error}), 404 if error == "Bien non trouvé" else 500
    
    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

@app.route('/api/property-reports/generate', methods=['POST'])
def generate_property_presentation_report():
    try:
        logging.info("Requête reçue à /api/property-reports/generate")
        log_to_file("Début de la génération du rapport de présentation immobilière")
        form_data = request.json
        logging.debug(f"Données reçues : {form_data}")
        log_to_file(f"Données du formulaire reçues : {form_data}")

        # Récupération des champs du nouveau questionnaire
        civility = form_data.get('civility', '')
        client_name = form_data.get('client-name', 'Client')
        report_date = form_data.get('report-date', datetime.now().strftime('%Y-%m-%d'))
        agency_email = form_data.get('agency-email', '')
        agency_phone = form_data.get('agency-phone', '')
        property_type = form_data.get('property-type', '')
        property_subtype = form_data.get('property-subtype', '')
        address_line1 = form_data.get('address-line1', '')
        address_line2 = form_data.get('address-line2', '')
        city = form_data.get('city', '')
        region = form_data.get('region', '')
        postal_code = form_data.get('postal-code', '')
        country = form_data.get('country', '')
        location_details = form_data.get('location-details', '')
        property_area = form_data.get('property-area', '')
        property_highlights = form_data.get('property-highlights', '')
        property_bedrooms = form_data.get('property-bedrooms', '')
        property_spaces = form_data.get('propertySpaces', [])
        property_bathrooms = form_data.get('property-bathrooms', '')
        kitchen_type = form_data.get('kitchen-type', '')
        dining_kitchen = form_data.get('dining-kitchen', '')
        property_parking = form_data.get('property-parking', '')
        covered_parking = form_data.get('covered-parking', '')
        property_land_area = form_data.get('property-land-area', '')
        pool = form_data.get('pool', '')
        property_renovations = form_data.get('property-renovations', '')
        shops_distance = form_data.get('shops-distance', '')
        primary_schools_distance = form_data.get('primary-schools-distance', '')
        secondary_schools_distance = form_data.get('secondary-schools-distance', '')
        transport_distance = form_data.get('transport-distance', '')
        property_price = form_data.get('property-price', '')
        negotiation = form_data.get('negotiation', '')
        property_additional_info = form_data.get('property-additional-info', '')
        local_factors = form_data.get('localFactors', [])
        language = form_data.get('report-language', 'fr')

        # Préparation du PDF
        PDF_FOLDER = "./pdf_reports/"
        os.makedirs(PDF_FOLDER, exist_ok=True)
        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_presentation_{client_name.replace(' ', '_')}.pdf")
        doc = SimpleDocTemplate(pdf_filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
        elements = []
        styles = getSampleStyleSheet()

        # PAGE DE GARDE
        cover_title_style = ParagraphStyle(
            'CoverTitle',
            fontSize=28,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor("#00C7C4"),
            alignment=1,
            spaceAfter=24
        )
        cover_subtitle_style = ParagraphStyle(
            'CoverSubtitle',
            fontSize=18,
            fontName='Helvetica',
            textColor=colors.HexColor("#1d3557"),
            alignment=1,
            spaceAfter=12
        )
        cover_info_style = ParagraphStyle(
            'CoverInfo',
            fontSize=12,
            fontName='Helvetica',
            textColor=colors.HexColor("#1d3557"),
            alignment=1,
            spaceAfter=8
        )
        elements.append(Spacer(1, 100))
        elements.append(Paragraph("Rapport de Présentation Immobilière", cover_title_style))
        elements.append(Paragraph(f"Présenté à : {civility} {client_name}", cover_subtitle_style))
        elements.append(Paragraph(f"Date du rapport : {report_date}", cover_info_style))
        elements.append(Paragraph(f"Adresse du bien : {address_line1} {address_line2}, {postal_code} {city}, {country}", cover_info_style))
        elements.append(Paragraph(f"Type de bien : {property_type} - {property_subtype}", cover_info_style))
        elements.append(Spacer(1, 60))
        elements.append(Paragraph(f"Agence : {agency_email} / {agency_phone}", cover_info_style))
        elements.append(PageBreak())

        # TABLE D'INFORMATIONS DU CLIENT
        add_section_title(elements, "Informations du Client Acheteur")
        client_info_data = [
            ["Civilité", civility],
            ["Nom / Prénom", client_name],
            ["E-mail agence", agency_email],
            ["Téléphone agence", agency_phone],
            ["Date du rapport", report_date],
            ["Type de bien", property_type],
            ["Sous-type", property_subtype],
            ["Adresse", f"{address_line1} {address_line2}"],
            ["Ville", city],
            ["Région", region],
            ["Code Postal", postal_code],
            ["Pays", country],
            ["Superficie habitable (m²)", property_area],
            ["Nombre de chambres", property_bedrooms],
            ["Nombre de salles de bain", property_bathrooms],
            ["Espaces complémentaires", ', '.join(property_spaces) if property_spaces else 'Aucun'],
            ["Cuisine", kitchen_type],
            ["Cuisine dinatoire", dining_kitchen],
            ["Parking (nb)", property_parking],
            ["Parking couvert", covered_parking],
            ["Superficie du terrain (m²)", property_land_area],
            ["Piscine/piscinable", pool],
            ["Prix de vente (€)", property_price],
            ["Marge de négociation", negotiation],
        ]
        t = Table(client_info_data, colWidths=[200, 300])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#00C7C4")),
            ('TEXTCOLOR', (0,0), (0,-1), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # Génération des sections dynamiques du rapport (comme dans generate_report)
        # On adapte le prompt pour chaque section en fonction des nouveaux champs
        summary = f"""
Résumé des informations fournies par le client :\n\n"""
        summary += f"Civilité : {civility}\nNom / Prénom : {client_name}\nType de bien : {property_type} - {property_subtype}\nAdresse : {address_line1} {address_line2}, {postal_code} {city}, {country}\nSuperficie : {property_area} m²\nChambres : {property_bedrooms}\nSalles de bain : {property_bathrooms}\nEspaces complémentaires : {', '.join(property_spaces) if property_spaces else 'Aucun'}\nCuisine : {kitchen_type}\nCuisine dinatoire : {dining_kitchen}\nParking : {property_parking}\nParking couvert : {covered_parking}\nSuperficie du terrain : {property_land_area}\nPiscine/piscinable : {pool}\nPrix de vente : {property_price} €\nMarge de négociation : {negotiation}\n"""
        if property_highlights:
            summary += f"Points forts : {property_highlights}\n"
        if property_renovations:
            summary += f"Travaux à prévoir : {property_renovations}\n"
        if property_additional_info:
            summary += f"Infos complémentaires : {property_additional_info}\n"
        if location_details:
            summary += f"Détails sur la zone : {location_details}\n"
        summary += f"\nDistances :\nCommerces : {shops_distance}\nÉcoles primaires : {primary_schools_distance}\nÉcoles secondaires : {secondary_schools_distance}\nTransports : {transport_distance}\n"

        # Mapping langue
        language_mapping = {
            'fr': 'Français',
            'en': 'Anglais',
        }
        language_name = language_mapping.get(language, 'Français')

        # Définition des sections du rapport
        sections = [
            ("Présentation du bien", 200),
            ("Analyse du quartier et de la zone", 250),
            ("Comparaison avec le marché local", 300),
            ("Points forts et axes d'amélioration", 200),
            ("Recommandations pour l'acheteur", 200),
        ]

        # Génération des sections avec OpenAI
        for section_title, min_words in sections:
            section_prompt = f"""
{summary}
La langue du rapport doit être : {language_name}.

Votre tâche est de générer la section '{section_title}' du rapport de présentation immobilière, en fournissant des informations de qualité professionnelle adaptées aux données du bien présenté. Suivez scrupuleusement les consignes suivantes :

- Structure claire, pas de répétition d'informations d'autres sections.
- Si pertinent, insérer des tableaux dynamiques en Markdown (format OpenAI).
- Pour chaque tableau, ajouter une description explicative.
- Minimum {min_words} mots pour cette section.
- Adapter l'analyse à la ville et au quartier ({city}, {region}).
- Prendre en compte les facteurs locaux importants sélectionnés : {', '.join(local_factors) if local_factors else 'Aucun'}.
- Mettre en avant les points forts du bien et les distances aux commodités.
- Pour la section "Comparaison avec le marché local", inclure un tableau comparatif avec d'autres biens similaires dans la ville.
- Pour la section "Recommandations", donner des conseils personnalisés à l'acheteur.
"""
            section_content = generate_section(client, section_prompt)
            if section_content and hasattr(section_content[0], "getPlainText"):
                first_text = section_content[0].getPlainText().strip().lower()
                if first_text == section_title.strip().lower():
                    section_content.pop(0)
            add_section_title(elements, section_title)
            elements.extend(section_content)
            elements.append(PageBreak())

        doc.build(elements)
        logging.info(f"Rapport généré avec succès : {pdf_filename}")
        log_to_file(f"Rapport généré avec succès : {pdf_filename}")

        return send_file(pdf_filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Erreur lors de la génération du rapport de présentation : {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
