from flask import Flask, request, send_file, jsonify
from openai import OpenAI
import os
import logging
import ssl
import unicodedata
import re
from flask_cors import CORS
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from PIL import Image as PILImage
import sys
from datetime import datetime
import tempfile

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
    openai.api_key = os.getenv("OPENAI_API_KEY")

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
    text = re.sub(r'(?<!\d)\.(?!\d|\)|\s[A-Z]|\s[a-z])(?!$)', '.<br/><br/>', text)
    text = re.sub(r':(?!\s?\d|\))(?!$)', ':<br/><br/>', text)
    return text

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

def add_text(elements, text):
    styles = getSampleStyleSheet()
    normal_style = ParagraphStyle(
        'NormalText',
        fontSize=12,
        fontName='Helvetica',
        alignment=0,
        leading=16,
    )
    elements.append(Paragraph(text, normal_style))
    elements.append(Spacer(1, 12))

def add_table(elements, data, column_widths=None):
    if column_widths is None:
        column_widths = [2 * inch] * len(data[0])
    table = Table(data, colWidths=column_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#00C7C4")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(KeepTogether(table))
    elements.append(Spacer(1, 12))

def resize_image(image_path, output_path, target_size=(469, 716)):
    with PILImage.open(image_path) as img:
        img = img.resize(target_size, PILImage.LANCZOS)
        img.save(output_path)

def generate_section(client, section_prompt, max_tokens=1500):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Vous êtes un expert en analyse financière et immobilière En tant qu'expert immobilier, générez un rapport détaillé avec des données chiffrées, des analyses spécifiques et des tableaux statistiques pour la ville mentionnée, en incluant l'impact des écoles, les recommandations de quartiers, les tendances du marché et les prévisions, tout en adaptant l'analyse aux critères du client et aux spécificités locales, dans un style professionnel et objectif."},
            {"role": "user", "content": section_prompt}
        ],
        max_tokens=max_tokens,
        temperature=0.5
    )
    return clean_text(response.choices[0].message.content)

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

@app.route('/')
def home():
    return "Bienvenue sur le serveur Flask. L'API est prête à recevoir des requêtes !"

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
            ("Analyse du produit/service", 300),
            ("Évaluation des risques", 350),
            ("Conclusion et recommandations", 300)
        ]

        pdf_filename = os.path.join(PDF_FOLDER, f"rapport_{name.replace(' ', '_')}.pdf")
        doc = SimpleDocTemplate(pdf_filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)

        elements = []
        styles = getSampleStyleSheet()

        cover_images = [
            "cover_image.png",
            "cover_image1.png",
            "cover_image2.png",
            "cover_image3.png"
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

            Générez la section '{section_title}' du rapport d'analyse. 
            Cette section doit contenir au minimum {min_words} mots.
            """
            section_content = generate_section(client, section_prompt)
            add_section_title(elements, section_title)
            add_text(elements, section_content)

            if section_title == "Analyse du produit/service":
                elements.append(PageBreak())
                add_section_title(elements, "Évolution du Prix du Bien Recherché (2020-2024)")
                data = [
                    ["Année", "Valeur estimée (EUR)", "Variation annuelle (%)"],
                    ["2020", "1,000,000", "+5.0"],
                    ["2021", "1,050,000", "+5.0"],
                    ["2022", "1,102,500", "+5.0"],
                    ["2023", "1,157,625", "+5.0"],
                    ["2024", "1,215,506", "+5.0"]
                ]
                add_table(elements, data, [2 * inch, 2 * inch, 2 * inch])

                elements.append(PageBreak())
                add_section_title(elements, "Évolution des Prix de l'Immobilier (2020-2024)")
                additional_data_1 = [
                    ["Année", "Prix moyen au m² (EUR)", "Variation annuelle (%)"],
                    ["2020", "5,700", "+4.5"],
                    ["2021", "5,985", "+5.0"],
                    ["2022", "6,285", "+5.0"],
                    ["2023", "6,600", "+5.0"],
                    ["2024", "6,930", "+5.0"]
                ]
                add_table(elements, additional_data_1, [2 * inch, 2 * inch, 2 * inch])

                elements.append(PageBreak())
                add_section_title(elements, "Caractéristiques et leur Impact sur la Valeur")
                additional_data_2 = [
                    ["Caractéristique", "Impact sur la Valeur (%)", "Justification"],
                    ["Cuisine fermée", "+10", "Pratique et très prisée dans l'immobilier de luxe"],
                    ["Piscine", "+15", "Élément de confort majeur"],
                    ["Parking couvert", "+5", "Atout en centre-ville"]
                ]
                add_table(elements, additional_data_2, [2 * inch, 2 * inch, 3 * inch])

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