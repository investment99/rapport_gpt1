from flask import Flask, request, send_file, jsonify, url_for
from openai import OpenAI
import os
import logging
import ssl
import unicodedata
from flask_cors import CORS
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from PIL import Image as PILImage
from datetime import datetime
import tempfile
import markdown2
from bs4 import BeautifulSoup

# Désactiver la vérification SSL (à utiliser avec précaution)
ssl._create_default_https_context = ssl._create_unverified_context

# Configurer le logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

# Créer l'application Flask
app = Flask(__name__)
CORS(app)
app.config['JSON_AS_ASCII'] = False

def log_to_file(message):
    """Journaliser les messages dans un fichier"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("app_log.txt", "a") as log_file:
        log_file.write(f"{timestamp} - {message}\n")

@app.route('/test_key', methods=['GET'])
def test_key():
    """Tester la clé API OpenAI"""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return f"Key loaded successfully: {api_key[:6]}...hidden", 200
    return "API key not found", 500

# Initialiser le client OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Créer le dossier pour les rapports PDF
PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

def clean_text(text):
    """Nettoyer le texte des caractères spéciaux"""
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
    """Convertir le Markdown en éléments ReportLab"""
    elements = []
    html_content = markdown2.markdown(md_text)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for element in soup:
        if element.name == 'p':
            para = Paragraph(clean_text(str(element)), getSampleStyleSheet()['BodyText'])
            elements.append(para)
            elements.append(Spacer(1, 12))
        elif element.name == 'table':
            data = []
            for row in element.find_all('tr'):
                cols = row.find_all(['td', 'th'])
                data.append([col.get_text() for col in cols])
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 12))
        elif element.name in ['h1', 'h2', 'h3']:
            para = Paragraph('<{}>{}</{}>'.format(element.name, clean_text(element.get_text()), element.name), getSampleStyleSheet()[element.name.capitalize()])
            elements.append(para)
            elements.append(Spacer(1, 12))
    return elements

def add_section_title(elements, title):
    """Ajouter un titre de section au PDF"""
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

def generate_section(client, section_prompt, max_tokens=1500):
    """Générer une section du rapport via OpenAI"""
    logging.info(f"Generating section with prompt: {section_prompt}")
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Vous êtes un expert de renommée mondiale en analyse financière et immobilière. Fournissez un rapport détaillé avec des données chiffrées, des tableaux, des graphiques et des analyses approfondies, en format Markdown."},
            {"role": "user", "content": section_prompt}
        ],
        max_tokens=max_tokens,
        temperature=0.5
    )
    logging.debug(f"API response: {response}")
    return markdown_to_elements(response.choices[0].message.content)

def generate_market_data(investment_sector, city):
    """Générer des données de marché basées sur le secteur et la ville"""
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
    """Route d'accueil"""
    if request.method == 'POST':
        return generate_report()
    return "Bienvenue sur le serveur Flask. L'API est prête à recevoir des requêtes !"

def resize_image(image_path, output_path, target_size=(469, 716)):
    """Redimensionner une image"""
    with PILImage.open(image_path) as img:
        img = img.resize(target_size, PILImage.LANCZOS)
        img.save(output_path)

@app.route('/generate_report', methods=['POST'])
def generate_report():
    """Générer un rapport PDF basé sur les données du formulaire"""
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
            # Génération du prompt pour OpenAI en utilisant les données spécifiques du client
            section_prompt = f"""
            Résumé des informations fournies par le client :

            Nom : {name}
            Secteur d'investissement : {investment_sector}
            Adresse : {address}
            Email : {email}
            Téléphone : {phone}
            Ville : {city}

            Données spécifiques au marché immobilier à {city} :
            - Prix moyen au mètre carré :
              {', '.join([f"{quartier}: {prix} EUR" for quartier, prix in market_data.get('prix_moyen', {}).items()])}
            - Taux d'évolution des prix : {market_data.get('evolution_prix', 'Non spécifié')}%.
            - Quartiers en développement : {', '.join(market_data.get('quartiers_developpement', []))}.
            - Segmentation du marché :
              {', '.join([f"{cat}: {part}%" for cat, part in market_data.get('segmentation', {}).items()])}.

            Contexte :
            Le client souhaite un rapport professionnel pour évaluer les opportunités d'investissement dans l'immobilier résidentiel ou commercial à {city}. L'objectif est de fournir des recommandations personnalisées basées sur des données chiffrées et des analyses locales.

            Votre tâche :
            Générez la section '{section_title}' du rapport d'analyse. Cette section doit :
            1. Contenir au minimum {min_words} mots.
            2. Être structurée de manière claire avec des sous-sections (si pertinent).
            3. Intégrer des données chiffrées du marché, des analyses qualitatives, et des exemples concrets.
            4. Inclure des recommandations adaptées aux objectifs du client.

            Ton attendu : Clair, professionnel et démontrant une expertise approfondie en immobilier.
            """

            # Génération du contenu de la section via OpenAI
            section_content = generate_section(client, section_prompt)

            # Ajout du titre de la section au PDF
            add_section_title(elements, section_title)

            # Intégration du contenu généré dans le rapport
            elements.extend(section_content)  # Ajoutez les éléments Markdown convertis ici

            # Si la section est "Analyse du marché", ajouter un tableau
            if section_title.lower() == "analyse du marché":
                table_data = [["Quartier", "Prix moyen au m² (EUR)"]]
                for quartier, prix in market_data.get("prix_moyen", {}).items():
                    table_data.append([quartier, f"{prix} EUR"])
                
                # Définir le style du tableau
                table_style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#00C7C4")),
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
                table = Table(table_data, style=table_style)
                elements.append(table)
                elements.append(Spacer(1, 12))

            # Ajout d'un saut de page après chaque section
            elements.append(PageBreak())

        # Construire le document PDF
        doc.build(elements)
        logging.info(f"Rapport généré avec succès : {pdf_filename}")
        log_to_file(f"Rapport généré avec succès : {pdf_filename}")

        return send_file(pdf_filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Erreur lors de la génération du rapport : {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)