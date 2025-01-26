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

            Votre tâche est de générer la section '{section_title}' du rapport d'analyse qui doit comporter des informations de qualité professionnelle. Le rapport doit inclure :

- Une introduction succincte du contexte général.
- Des insights précis et basés sur des chiffres, comme "le prix moyen au mètre carré à {address} est de ...", et des comparaisons historiques (par exemple, l'évolution sur les 5 dernières années).
- Des recommandations spécifiques aux critères de {name}, en s'appuyant sur les aspirations mentionnées telles que {investment_sector}.
- Intégrez au moins un tableau ou graphique (format texte Markdown) représentant des statistiques pertinentes pour le quartier ou les tendances démographiques.
- D'autres détails utiles pourraient inclure l'impact des infrastructures locales, des comparaisons inter-quartiers, et des projections à moyen terme.

Assurez-vous que le libellé est clair, précis, et bien structuré avec un minimum de {min_words} mots.
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