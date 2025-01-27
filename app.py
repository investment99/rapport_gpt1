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
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    replacements = {
        '€': 'EUR', '£': 'GBP', '©': '(c)', '®': '(R)', '™': '(TM)',
        '…': '...', '—': '-', '–': '-', '"': '"', '"': '"', "'": "'", "'": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.encode('ascii', errors='ignore').decode('ascii')
    return text

def markdown_to_elements(md_text):
    elements = []
    lines = md_text.split('\n')
    table_data = []
    for line in lines:
        if "|" in line and "---" not in line:
            # C'est une ligne de tableau
            row = line.split('|')
            table_data.append([cell.strip() for cell in row if cell.strip()])
        else:
            if table_data:
                # Traiter le tableau accumulé une fois qu'une ligne non-tableau est rencontrée
                table_style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 11),
                    ('TOPPADDING', (0, 1), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ])
                elements.append(Table(table_data, style=table_style))
                table_data = []

            if line.strip():
                paragraph = Paragraph(clean_text(line), getSampleStyleSheet()['BodyText'])
                elements.append(paragraph)
                elements.append(Spacer(1, 12))

    if table_data:
        # Ajouter le dernier tableau s'il y en a un
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ])
        elements.append(Table(table_data, style=table_style))
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

        client_info = {key: value for key, value in form_data.items()}
        market_data = generate_market_data(investment_sector, city)

        summary = "Résumé des informations fournies par le client :\n\n"
        for key, value in client_info.items():
            summary += f"{key}: {value}\n"

        market_data_str = f"\nDonnées spécifiques du marché :\n{market_data}\n"

        sections = [
            ("Introduction", 200),
            ("Contexte", 250),
            ("Secteur d'investissement", 300),
            ("Analyse du marché", 400),
            ("Analyse du produit", 300),
            ("Évaluation des risques", 350),
            ("Conclusion et recommandations", 300)
        ]

        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_{name.replace(' ', '_')}.pdf")
        doc = SimpleDocTemplate(pdf_filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)

        elements = []
        styles = getSampleStyleSheet()

        cover_images = [
            "static/cover_image.png",
            "static/cover_image1.png",
            "static/cover_image2.png",
            "static/cover_image3.png"
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
            section_prompt = f"""
            {summary}

            {market_data_str}
Votre tâche est de générer la section '{section_title}' du rapport d'analyse immobilier, en fournissant des informations de qualité professionnelle adaptées et choisie par le client. Suivez scrupuleusement les consignes suivantes :

---

### Instructions Générales

1. **Structure et Clarté** :
   - Ne répétez pas les informations des autres sections.
   - Évitez les sous-menus ou sous-sections supplémentaires.

2. **Utilisation des Tableaux** :
   - Tous les tableaux doivent être générés dynamiquement par OpenAI en fonction des données pour la ville {address}.
   - Les tableaux doivent être insérés tels qu'ils sont générés, au format Markdown.
   - Ne reconstruisez pas les tableaux ou leur format.
   - Assurez-vous que chaque tableau soit unique à la section et suivi d'une description claire expliquant son contenu et sa pertinence.

3. **Organisation des Sections** :
   - **Introduction** : Vue d'ensemble des objectifs d'investissement et aperçu rapide du marché local.
   - **Contexte** : Analyse historique et démographique détaillée de la ville {address}, incluant des données sur la population, les infrastructures et le développement économique.
   - **Secteur d'investissement** : Inclure l'évolution des prix au m² (5 dernières années) et le rendement locatif moyen (2020-2025) pour la ville {address}.
   - **Analyse du marché** : Inclure l'évolution des prix immobiliers (2020-2025), un tableau comparatif des quartiers dans la ville {address} (prix au m², rendement locatif, distances), et les facteurs influençant le marché local.
   - **Analyse du produit** : Évaluation des caractéristiques spécifiques du produit immobilier ciblé.
   - **Évaluation des risques** : Analyse des risques liés à l'investissement dans la ville {address}.
   - **Conclusion et recommandations** : Synthèse des données clés et recommandations claires pour le client.

4. **Détails à Inclure** :
   - Donnez un aperçu précis des infrastructures, des quartiers importants et des facteurs économiques spécifiques à {address}.
   - Ajoutez des données pertinentes sur la population, la demande locative, et les tendances démographiques.
   - Fournissez des insights basés sur des chiffres, comme "le prix moyen au m² à {address} est de ...", et comparez plusieurs quartiers.
   - Ajoutez au moins une projection à moyen terme pour les prix immobiliers dans la ville {address}.

5. **Exemple attendu pour les tableaux générés dynamiquement** :
   - **Secteur d'investissement** : Tableau de l'évolution des prix au m² sur 5 ans et du rendement locatif moyen.
   - **Analyse du marché** : Tableau comparatif des quartiers dans la ville choisie ({address}) avec des colonnes adaptées aux données locales (prix, rendement locatif, distances, etc.).

---

### Instructions par Section

#### **1. Introduction**
Générez une introduction qui inclut :
- Une présentation des objectifs d'investissement du formulaire client(exemple : investir dans un appartement de 120m² à {address} pour un usage locatif).
- Une explication rapide de l'importance du marché local pour cet investissement.
- Aucun tableau dans cette section.

---

#### **2. Contexte**
Générez une analyse détaillée du contexte local, incluant :
- Une présentation générale de la ville {address} : population, attractivité économique, infrastructures clés.
- Une analyse des tendances immobilières et démographiques sur les 5 dernières années.
- Aucun tableau dans cette section, uniquement des informations textuelles détaillées.

---

#### **3. Secteur d'investissement**
Générez une analyse détaillée du secteur d'investissement, incluant :
- Un tableau dynamique montrant l'évolution des prix moyens au m² dans la ville {address} sur les 5 dernières années.
- Un tableau dynamique illustrant le rendement locatif moyen de la ville {address} pour la période 2020-2025.
- Une description claire expliquant les tendances et leur pertinence pour l'investissement.

---

#### **4. Analyse du marché**
Générez une analyse approfondie du marché immobilier local, incluant :
- Un tableau dynamique montrant l'évolution des prix immobiliers à {address} sur la période 2020-2025.
- Un tableau comparatif dynamique entre différents quartiers de {address}, avec les colonnes suivantes :
  - Prix moyen au m².
  - Rendement locatif (%).
  - Distances moyennes aux commerces et écoles.
- Une analyse expliquant les facteurs influençant les prix et les rendements locatifs.

---

#### **5. Analyse du produit**
Générez une analyse détaillée du produit immobilier ciblé par le client, incluant :
- Une description des caractéristiques de l'appartement cible (taille, emplacement, infrastructures à proximité).
- Un tableau montrant les prix moyens au m² pour des biens similaires dans le quartier ciblé à {address}.

---

#### **6. Évaluation des risques**
Générez une évaluation complète des risques liés à l'investissement, incluant :
- Une analyse des risques de marché (vacance locative, fluctuations des prix).
- Un tableau illustrant les variations annuelles des prix au m² pour évaluer la stabilité du marché.

---

#### **7. Conclusion et recommandations**
Générez une conclusion complète, incluant :
- Une synthèse des données clés (prix au m², rendement locatif, etc.).
- Une recommandation claire sur l'opportunité d'investir à {address}.
- Un tableau final illustrant l'évolution des prix au m² sur les 5 dernières années.

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
            section_content = generate_section(client, section_prompt)
            add_section_title(elements, section_title)
            elements.extend(section_content)  # Ajoutez les éléments Markdown convertis ici

            elements.append(PageBreak())

        doc.build(elements)
        logging.info(f"Rapport généré avec succès : {pdf_filename}")
        log_to_file(f"Rapport généré avec succès : {pdf_filename}")

        return send_file(pdf_filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Erreur lors de la génération du rapport : {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)