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
                    # Intégrer les facteurs locaux directement dans les instructions pour l'analyse du produit
                    section_prompt = section_prompt.replace(
                        "- **Analyse du produit** : Évaluation des caractéristiques spécifiques du produit immobilier ciblé.",
                        "- **Analyse du produit** : Évaluation des caractéristiques spécifiques du produit immobilier ciblé, incluant une analyse EXTRÊMEMENT PRÉCISE et DÉTAILLÉE des facteurs locaux importants."
                    )
                    
                    # Ajuster la section des instructions pour l'analyse du produit
                    product_analysis_index = section_prompt.find("#### **5. Analyse du produit**")
                    if product_analysis_index != -1:
                        # Trouver la fin des instructions pour l'analyse du produit
                        next_section_index = section_prompt.find("---", product_analysis_index)
                        if next_section_index != -1:
                            # Insérer les instructions pour les facteurs locaux juste avant la fin de la section
                            factors_instructions = f"""

En plus de l'analyse du produit, vous DEVEZ IMPÉRATIVEMENT inclure une sous-section intitulée "FACTEURS LOCAUX IMPORTANTS" qui analyse EN DÉTAIL et avec une EXTRÊME PRÉCISION les facteurs suivants qui sont importants pour le client.

{local_factors_prompt.strip()}

EXIGENCES NON NÉGOCIABLES pour cette section:
1. Ne générez JAMAIS d'informations génériques - fournissez UNIQUEMENT des données PRÉCISES et VÉRIFIABLES
2. Utilisez SYSTÉMATIQUEMENT des CHIFFRES EXACTS (distances, nombres, pourcentages, etc.)
3. Mentionnez les NOMS SPÉCIFIQUES de tous les établissements, lignes de transport, commerces, etc.
4. Si une information précise vous semble manquante, précisez-le explicitement
5. Cette section doit absolument refléter une connaissance APPROFONDIE et LOCALE du quartier, comme celle d'un agent immobilier expérimenté travaillant dans ce secteur depuis de nombreuses années
"""
                            section_prompt = section_prompt[:next_section_index] + factors_instructions + section_prompt[next_section_index:]
            
            section_content = generate_section(client, section_prompt)
    
            # Si le premier élément est un Paragraph dont le texte correspond exactement au titre, le supprimer
            if section_content and hasattr(section_content[0], "getPlainText"):
                first_text = section_content[0].getPlainText().strip().lower()
                if first_text == section_title.strip().lower():
                    section_content.pop(0)
    
            # Ajout du titre de section dans le document
            add_section_title(elements, section_title)
            elements.extend(section_content)  # Ajoute le contenu de la section sans duplication du titre
            
            # Ajout d'un espacement après chaque section pour améliorer la lisibilité
            elements.append(Spacer(1, 20))
            
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
    
    local_factors_prompt = ""
    
    for factor in form_data.get('localFactors', []):
        if factor in factor_descriptions:
            if factor == 'transport':
                local_factors_prompt += f"""- **{factor_descriptions[factor]}**: 
Pour les transports en commun, vous DEVEZ IMPÉRATIVEMENT lister TOUS les moyens de transport du quartier avec leurs détails précis:
1. Métro: indiquer TOUTES les stations dans un rayon de 1km avec les NUMÉROS EXACTS des lignes (ex: Ligne 4, Ligne 12) et les DISTANCES PRÉCISES en mètres et minutes de marche
2. Bus: indiquer TOUS les numéros de lignes précis (ex: Bus 38, 67, 96) avec les noms des arrêts et leurs emplacements exacts
3. RER/Trains: indiquer les stations, numéros de lignes (ex: RER A, RER B) et destinations accessibles
4. Tramway: indiquer les lignes précises si disponibles dans le secteur
5. Préciser la FRÉQUENCE DES PASSAGES (ex: toutes les 3 minutes en heure de pointe)
6. Indiquer les TEMPS DE TRAJET précis vers les principaux pôles (gares, centres d'affaires, centre-ville)
Répondez avec une PRÉCISION EXTRÊME et des DONNÉES CHIFFRÉES pour chaque information.

"""
            elif factor == 'schools':
                local_factors_prompt += f"""- **{factor_descriptions[factor]}**: 
Pour les écoles, vous DEVEZ IMPÉRATIVEMENT:
1. Lister TOUS les établissements scolaires dans un rayon de 1,5km: crèches, maternelles, primaires, collèges, lycées et établissements supérieurs
2. Pour CHAQUE établissement, préciser:
   - Le NOM EXACT de l'établissement
   - Son TYPE précis (public/privé/international)
   - Sa DISTANCE EXACTE en mètres et minutes à pied
   - Ses SPÉCIFICITÉS (sections internationales, options spéciales)
   - Ses RÉSULTATS académiques chiffrés quand disponibles (% réussite bac, classements)
3. Indiquer la RÉPUTATION de chaque établissement avec des données objectives
4. Mentionner les établissements d'excellence ou spécialisés dans le secteur
Répondez avec une PRÉCISION EXTRÊME et des DONNÉES CHIFFRÉES pour chaque information.

"""
            elif factor == 'shops':
                local_factors_prompt += f"""- **{factor_descriptions[factor]}**: 
Pour les commerces et services, vous DEVEZ IMPÉRATIVEMENT:
1. Lister TOUS les commerces essentiels dans un rayon de 1km avec leurs NOMS EXACTS et DISTANCES PRÉCISES:
   - Supermarchés/épiceries (préciser les enseignes exactes, ex: Carrefour City, Monoprix, etc.)
   - Boulangeries (avec noms spécifiques)
   - Pharmacies (nombres et emplacements précis)
   - Restaurants (types de cuisine et gammes de prix)
   - Services médicaux (médecins, spécialistes, centres médicaux)
2. Indiquer les CENTRES COMMERCIAUX avec:
   - Leurs NOMS EXACTS
   - Le NOMBRE PRÉCIS de boutiques
   - Les ENSEIGNES PRINCIPALES
   - La DISTANCE EXACTE en mètres et minutes
3. Préciser les MARCHÉS avec leurs JOURS et HORAIRES exacts
4. Évaluer la DENSITÉ COMMERCIALE par rapport aux quartiers voisins
5. Indiquer les COMMERCES SPÉCIALISÉS remarquables
Répondez avec une PRÉCISION EXTRÊME et des DONNÉES CHIFFRÉES pour chaque information.

"""
            elif factor == 'security':
                local_factors_prompt += f"""- **{factor_descriptions[factor]}**: 
Pour la sécurité du quartier, vous DEVEZ IMPÉRATIVEMENT fournir:
1. Des DONNÉES CHIFFRÉES précises sur la criminalité:
   - Taux d'infractions par catégorie (cambriolages, agressions, incivilités)
   - COMPARAISON EXACTE avec la moyenne de la ville et des quartiers voisins
   - ÉVOLUTION sur les 3 dernières années avec pourcentages précis
2. Présence policière et sécuritaire:
   - Distance du commissariat le plus proche (en mètres exacts)
   - Fréquence des patrouilles
   - Présence de caméras de surveillance
3. Appréciation objective de l'ambiance:
   - Sécurité ressentie de jour et de nuit
   - Zones plus sensibles identifiées avec précision
   - Témoignages de résidents si disponibles
4. Facteurs influençant la sécurité:
   - Éclairage public
   - Configuration urbaine
   - Mixité sociale
Répondez avec une PRÉCISION EXTRÊME et des DONNÉES CHIFFRÉES pour chaque information.

"""
            elif factor == 'development':
                local_factors_prompt += f"""- **{factor_descriptions[factor]}**: 
Pour les projets urbains, vous DEVEZ IMPÉRATIVEMENT:
1. Lister TOUS les projets d'aménagement en cours ou prévus avec:
   - NOMS EXACTS des projets
   - DATES PRÉCISES (début/fin des travaux)
   - BUDGETS EXACTS en millions d'euros
   - NATURE DÉTAILLÉE (logements, commerces, infrastructures)
2. Pour chaque projet majeur, préciser:
   - Sa LOCALISATION EXACTE par rapport au bien
   - Son IMPACT QUANTIFIÉ sur les prix immobiliers
   - Les NOUVELLES INFRASTRUCTURES apportées
3. Détailler les projets de transport:
   - Nouvelles lignes/stations
   - Améliorations prévues
   - Calendrier précis de mise en service
4. Identifier les zones de développement prioritaires:
   - Quartiers en rénovation urbaine
   - Zones d'aménagement concerté (ZAC)
   - Pôles de croissance économique
5. Évaluer l'impact de ces projets sur l'attractivité future
Répondez avec une PRÉCISION EXTRÊME et des DONNÉES CHIFFRÉES pour chaque information.

"""
            elif factor == 'employment':
                local_factors_prompt += f"""- **{factor_descriptions[factor]}**: 
Pour le bassin d'emploi, vous DEVEZ IMPÉRATIVEMENT:
1. Identifier TOUS les employeurs majeurs du secteur:
   - NOMS EXACTS des entreprises/institutions
   - NOMBRE PRÉCIS d'employés par structure
   - SECTEURS D'ACTIVITÉ spécifiques
   - DISTANCE EXACTE en km et minutes de transport
2. Fournir des données économiques précises:
   - TAUX DE CHÔMAGE du secteur (comparé à la moyenne ville/région/pays)
   - REVENU MOYEN des habitants (chiffré exactement)
   - CROISSANCE ÉCONOMIQUE locale avec pourcentages précis
3. Détailler les zones d'activité:
   - Parcs d'entreprises, zones industrielles, centres d'affaires
   - Nombre exact d'entreprises et typologie
   - Accessibilité en transport (temps précis)
4. Analyser les perspectives d'évolution:
   - Secteurs en développement/déclin
   - Implantations futures confirmées
   - Projets économiques structurants
Répondez avec une PRÉCISION EXTRÊME et des DONNÉES CHIFFRÉES pour chaque information.

"""
            else:
                local_factors_prompt += f"""- **{factor_descriptions[factor]}**: 
Analysez ce facteur de manière extrêmement détaillée et précise avec des données chiffrées et factuelles.

"""
    
    return local_factors_prompt

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
