/**
 * Modèle d'implémentation pour intégrer la section "Facteurs locaux importants"
 * dans l'application rapport-gpt1
 */

// Fonction pour traiter les facteurs locaux et les intégrer dans le prompt OpenAI
function processLocalFactors(formData) {
  let localFactorsPrompt = '';
  
  // Vérifier si des facteurs locaux ont été sélectionnés
  if (formData.localFactors && formData.localFactors.length > 0) {
    // Traduire les codes en descriptions claires
    const factorDescriptions = {
      'transport': 'Transports en commun (métro, bus, tram, train)',
      'schools': 'Proximité des écoles et établissements éducatifs',
      'shops': 'Commerces et services de proximité',
      'security': 'Sécurité et tranquillité du quartier',
      'development': 'Projets urbains et développements futurs',
      'employment': 'Bassin d\'emploi et activité économique'
    };
    
    // Générer le texte du prompt pour ces facteurs
    localFactorsPrompt = '\n\n### FACTEURS LOCAUX IMPORTANTS\n';
    localFactorsPrompt += 'Le client accorde une importance particulière aux facteurs suivants. Veuillez les analyser en détail :\n';
    
    formData.localFactors.forEach(factor => {
      if (factorDescriptions[factor]) {
        localFactorsPrompt += `- ${factorDescriptions[factor]}\n`;
      }
    });
  }
  
  return localFactorsPrompt;
}

// Fonction pour intégrer la section des facteurs locaux dans le prompt principal
function integrateLocalFactorsInPrompt(existingPrompt, localFactorsPrompt) {
  // Si aucun facteur local n'est sélectionné, retourner le prompt existant
  if (!localFactorsPrompt) {
    return existingPrompt;
  }
  
  // Rechercher où insérer la section des facteurs locaux (après la section "Analyse du produit")
  // Cela suppose que le prompt existant contient une section nommée "Analyse du produit"
  const analyseProductIndex = existingPrompt.indexOf('### ANALYSE DU PRODUIT');
  
  if (analyseProductIndex !== -1) {
    // Trouver la fin de la section Analyse du produit (le début de la section suivante)
    const nextSectionIndex = existingPrompt.indexOf('###', analyseProductIndex + 1);
    
    if (nextSectionIndex !== -1) {
      // Insérer la section des facteurs locaux entre la section Analyse du produit et la section suivante
      return existingPrompt.substring(0, nextSectionIndex) + 
             localFactorsPrompt + 
             existingPrompt.substring(nextSectionIndex);
    } else {
      // Si pas de section suivante, ajouter à la fin
      return existingPrompt + localFactorsPrompt;
    }
  } else {
    // Si pas de section Analyse du produit, ajouter avant les recommandations
    const recommandationsIndex = existingPrompt.indexOf('### RECOMMANDATIONS');
    
    if (recommandationsIndex !== -1) {
      return existingPrompt.substring(0, recommandationsIndex) + 
             localFactorsPrompt + 
             existingPrompt.substring(recommandationsIndex);
    } else {
      // Si pas de section recommandations, ajouter à la fin
      return existingPrompt + localFactorsPrompt;
    }
  }
}

// Fonction pour formater la réponse OpenAI en intégrant les facteurs locaux sélectionnés
function formatReportWithLocalFactors(reportText, localFactors) {
  if (!localFactors || localFactors.length === 0) {
    // Si aucun facteur local n'est sélectionné, retourner le rapport tel quel
    return reportText;
  }
  
  // Définir les mots-clés pertinents pour chaque facteur local
  const factorKeywords = {
    'transport': ['transport', 'métro', 'bus', 'tram', 'gare', 'mobilité', 'déplacement'],
    'schools': ['école', 'collège', 'lycée', 'université', 'établissement scolaire', 'éducation'],
    'shops': ['commerce', 'boutique', 'magasin', 'supermarché', 'service', 'proximité'],
    'security': ['sécurité', 'tranquillité', 'criminalité', 'délinquance', 'surveillance'],
    'development': ['projet urbain', 'développement', 'construction', 'rénovation', 'aménagement'],
    'employment': ['emploi', 'travail', 'économique', 'entreprise', 'activité', 'bassin']
  };
  
  // Créer une fonction pour vérifier si une section doit être conservée
  function shouldKeepSection(sectionText, selectedFactors) {
    if (!selectedFactors || selectedFactors.length === 0) {
      return true; // Garder toutes les sections si aucun facteur n'est sélectionné
    }
    
    // Vérifier si le texte de la section contient des mots-clés correspondant aux facteurs sélectionnés
    return selectedFactors.some(factor => {
      const keywords = factorKeywords[factor] || [];
      return keywords.some(keyword => 
        sectionText.toLowerCase().includes(keyword.toLowerCase())
      );
    });
  }
  
  // Traiter le rapport pour conserver uniquement les sections pertinentes des facteurs locaux
  // Ce code est simplifié et devrait être adapté selon le format exact du rapport généré
  const sections = reportText.split('#### ');
  let formattedReport = sections[0]; // Conserver l'introduction
  
  for (let i = 1; i < sections.length; i++) {
    const section = sections[i];
    const sectionTitle = section.split('\n')[0];
    const sectionContent = section.substring(sectionTitle.length);
    
    // Si la section concerne les facteurs locaux, vérifier si elle doit être conservée
    if (sectionTitle.includes('facteur') || 
        sectionTitle.includes('local') ||
        sectionTitle.includes('transport') ||
        sectionTitle.includes('école') ||
        sectionTitle.includes('commerce') ||
        sectionTitle.includes('sécurité') ||
        sectionTitle.includes('projet') ||
        sectionTitle.includes('emploi')) {
      
      if (shouldKeepSection(section, localFactors)) {
        formattedReport += '#### ' + section;
      }
    } else {
      // Conserver les autres sections
      formattedReport += '#### ' + section;
    }
  }
  
  return formattedReport;
}

// Exemple d'utilisation dans le traitement du formulaire
function handleFormSubmission(formData) {
  // Récupérer les facteurs locaux sélectionnés
  const localFactors = formData.localFactors || [];
  
  // Générer le prompt pour les facteurs locaux
  const localFactorsPrompt = processLocalFactors(formData);
  
  // Intégrer au prompt principal (à adapter selon votre structure actuelle)
  const mainPrompt = generateMainPrompt(formData); // Fonction existante à adapter
  const fullPrompt = integrateLocalFactorsInPrompt(mainPrompt, localFactorsPrompt);
  
  // Appel à l'API OpenAI (à adapter selon votre structure actuelle)
  callOpenAI(fullPrompt)
    .then(response => {
      // Formater la réponse en intégrant les facteurs locaux
      const formattedReport = formatReportWithLocalFactors(response.text, localFactors);
      
      // Générer le PDF avec la réponse formatée
      return generatePDF(formattedReport);
    })
    .then(pdfBlob => {
      // Télécharger le PDF
      downloadPDF(pdfBlob);
    })
    .catch(error => {
      console.error('Erreur:', error);
    });
}

// Note: Ces fonctions sont des modèles à adapter selon la structure exacte
// de votre application rapport-gpt1 existante.
