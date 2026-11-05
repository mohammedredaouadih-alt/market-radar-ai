const form = document.getElementById('studyForm');
const resultsSection = document.getElementById('results');
const reportTitle = document.getElementById('reportTitle');
const executiveSummary = document.getElementById('executiveSummary');
const keyFindings = document.getElementById('keyFindings');
const insightsGrid = document.getElementById('insightsGrid');
const studyPlan = document.getElementById('studyPlan');
const recommendations = document.getElementById('recommendations');
const sourcesList = document.getElementById('sourcesList');
const reportMeta = document.getElementById('reportMeta');
const reportStatus = document.getElementById('reportStatus');
const reliabilityScore = document.getElementById('reliabilityScore');
const reliabilityTitle = document.getElementById('reliabilityTitle');
const reliabilityFactors = document.getElementById('reliabilityFactors');
const reliabilityDisclaimer = document.getElementById('reliabilityDisclaimer');
const formError = document.getElementById('formError');
const analyzeButton = document.getElementById('analyzeButton');
const studyList = document.getElementById('studyList');
const evidenceForm = document.getElementById('evidenceForm');
const evidenceAssessments = document.getElementById('evidenceAssessments');
const evidenceSearchStatus = document.getElementById('evidenceSearchStatus');
const evidenceFinding = document.getElementById('evidenceFinding');
const evidenceFormError = document.getElementById('evidenceFormError');
const addEvidenceButton = document.getElementById('addEvidenceButton');
let currentStudyId = null;
let currentEvidenceAssessments = [];

const evidenceCriterionLabels = {
  quality: 'Qualité des sources (30 %)',
  independence: 'Sources indépendantes (25 %)',
  freshness: 'Fraîcheur des données (25 %)',
  coherence: 'Cohérence des informations (20 %)',
};
const evidenceSourceLabels = {
  government: 'Organisme public',
  academic: 'Académique',
  international_organization: 'Organisation internationale',
  industry_report: 'Étude sectorielle',
  company_primary: 'Donnée primaire',
  news: 'Presse',
  other: 'Autre',
};

function updateStudyHistory(market, country) {
  const total = Number(document.getElementById('studyTotal').textContent) + 1;
  const today = new Intl.DateTimeFormat('fr-FR').format(new Date());
  const row = document.createElement('article');
  const marker = document.createElement('span');
  const copy = document.createElement('div');
  const title = document.createElement('strong');
  const detail = document.createElement('span');
  const arrow = document.createElement('span');

  row.className = 'study-row';
  marker.className = 'study-type';
  marker.textContent = (market || 'M').slice(0, 1).toUpperCase();
  copy.className = 'study-row-copy';
  title.textContent = market || 'Marché sans nom';
  detail.textContent = `${country || 'Zone non précisée'} · ${today}`;
  copy.append(title, detail);
  arrow.className = 'study-arrow';
  arrow.textContent = '↗';
  row.append(marker, copy, arrow);
  studyList.prepend(row);
  studyList.classList.remove('hidden');

  const emptyState = document.getElementById('emptyState');
  if (emptyState) emptyState.remove();
  document.getElementById('studyTotal').textContent = total;
  document.getElementById('navStudyCount').textContent = total;
  document.getElementById('recentCount').textContent = total;
  document.getElementById('lastActivity').textContent = today;
  document.getElementById('activityCaption').textContent = 'étude sauvegardée';
}

function renderList(target, items) {
  target.replaceChildren(...items.map((item) => {
    const element = document.createElement('li');
    element.textContent = item;
    return element;
  }));
}

function renderPlan(items) {
  studyPlan.replaceChildren(...items.map((item) => {
    const card = document.createElement('article');
    const title = document.createElement('h4');
    const description = document.createElement('div');
    card.className = 'plan-item';
    title.textContent = item.title;
    description.textContent = item.description;
    card.append(title, description);
    return card;
  }));
}

function renderInsights(items) {
  insightsGrid.replaceChildren(...items.map((item) => {
    const card = document.createElement('article');
    const label = document.createElement('div');
    const value = document.createElement('strong');
    const description = document.createElement('p');
    card.className = 'insight-card';
    label.className = 'label';
    label.textContent = item.title;
    value.textContent = item.value;
    description.textContent = item.description;
    card.append(label, value, description);
    return card;
  }));
}

function renderEvidence(items) {
  currentEvidenceAssessments = items;
  evidenceFinding.replaceChildren(...items.map((item, index) => {
    const option = document.createElement('option');
    option.value = index;
    option.textContent = item.conclusion;
    return option;
  }));
  evidenceAssessments.replaceChildren(...items.map((item) => {
    const card = document.createElement('article');
    const heading = document.createElement('h4');
    const score = document.createElement('strong');
    const criteria = document.createElement('ul');
    const sourceList = document.createElement('ul');
    const explanation = document.createElement('p');
    const warnings = document.createElement('ul');
    card.className = 'evidence-card';
    heading.className = 'evidence-conclusion';
    heading.textContent = item.conclusion;
    score.className = 'evidence-final-score';
    score.textContent = item.score === null ? 'Données insuffisantes' : `${Number(item.score).toLocaleString('fr-FR')}/100`;
    criteria.className = 'evidence-criteria';
    Object.entries(item.criteria || {}).forEach(([key, criterion]) => {
      const row = document.createElement('li');
      const name = document.createElement('span');
      const value = document.createElement('strong');
      name.textContent = evidenceCriterionLabels[key] || key;
      value.textContent = criterion.score === null
        ? '—'
        : `${Number(criterion.score).toLocaleString('fr-FR')}/100 · +${Number(criterion.contribution).toLocaleString('fr-FR')}`;
      row.append(name, value);
      criteria.append(row);
    });
    sourceList.className = 'evidence-source-list';
    (item.sources || []).forEach((source) => {
      const row = document.createElement('li');
      const link = document.createElement('a');
      const date = document.createElement('span');
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = source.title;
      date.textContent = `${source.published_at || 'Date non fournie'} · ${evidenceSourceLabels[source.source_type] || source.source_type}`;
      row.append(link, date);
      sourceList.append(row);
    });
    if (!item.sources || !item.sources.length) {
      const empty = document.createElement('li');
      empty.textContent = 'Aucune source documentée.';
      sourceList.append(empty);
    }
    explanation.className = 'evidence-explanation';
    explanation.textContent = item.explanation;
    warnings.className = 'evidence-warnings';
    (item.warnings || []).forEach((warning) => {
      const row = document.createElement('li');
      row.textContent = warning;
      warnings.append(row);
    });
    const progressTrack = document.createElement('div');
    progressTrack.className = 'evidence-progress';
    progressTrack.setAttribute('role', 'progressbar');
    progressTrack.setAttribute('aria-label', 'Evidence Score');
    progressTrack.setAttribute('aria-valuemin', '0');
    progressTrack.setAttribute('aria-valuemax', '100');
    const progress = document.createElement('span');
    if (item.score !== null) {
      progressTrack.setAttribute('aria-valuenow', String(item.score));
      progress.style.width = `${Math.max(0, Math.min(100, Number(item.score)))}%`;
    } else {
      progressTrack.setAttribute('aria-valuetext', 'Données insuffisantes');
      progress.classList.add('is-insufficient');
    }
    progressTrack.append(progress);
    card.append(heading, score, progressTrack, criteria, explanation, warnings);
    const sourceHeading = document.createElement('h5');
    sourceHeading.textContent = `Sources utilisées (${(item.sources || []).length})`;
    card.append(sourceHeading, sourceList);
    return card;
  }));
  evidenceForm.classList.toggle('hidden', items.length === 0);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  formError.textContent = '';
  analyzeButton.disabled = true;
  analyzeButton.querySelector('span').textContent = 'Analyse en cours…';

  const payload = new FormData();
  payload.append('company', document.getElementById('company').value);
  payload.append('country', document.getElementById('country').value);
  payload.append('market', document.getElementById('market').value);
  payload.append('question', document.getElementById('question').value);
  payload.append('objective', document.getElementById('objective').value);
  const dataFile = document.getElementById('dataFile').files[0];
  if (dataFile) payload.append('data_file', dataFile);

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Impossible de générer cette étude.');
    }

    reportTitle.textContent = data.title;
    const market = document.getElementById('market').value;
    const country = document.getElementById('country').value;
    const company = document.getElementById('company').value;
    reportMeta.textContent = `${market || 'Marché'} · ${country || 'Zone non précisée'} · ${company || 'Entreprise non précisée'}`;
    reliabilityScore.textContent = data.reliability_score;
    reliabilityTitle.textContent = `Couverture des données · ${data.reliability_label}`;
    renderList(reliabilityFactors, data.reliability_factors || []);
    reliabilityDisclaimer.textContent = data.reliability_disclaimer || '';
    if (data.uploaded_data) {
      reportMeta.textContent += ` · ${data.uploaded_data.filename} (${data.uploaded_data.row_count} lignes)`;
    }
    executiveSummary.textContent = data.executive_summary;
    renderList(keyFindings, data.key_findings || []);
    renderInsights(data.insights || []);
    renderPlan(data.study_plan || []);
    renderList(recommendations, data.recommendations || []);
    renderList(sourcesList, data.sources || []);
    currentStudyId = data.study_id;
    evidenceSearchStatus.textContent = data.evidence_search_message || '';
    renderEvidence(data.evidence_assessments || []);
    reportStatus.textContent = 'IA CONNECTÉE';
    updateStudyHistory(market, country);

    resultsSection.classList.remove('hidden');
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    formError.textContent = error.message || 'Une erreur est survenue. Réessayez.';
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.querySelector('span').textContent = 'Générer l’étude';
  }
});

evidenceForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  evidenceFormError.textContent = '';
  addEvidenceButton.disabled = true;
  try {
    const response = await fetch(`/api/studies/${currentStudyId}/evidence`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        finding_index: Number(evidenceFinding.value),
        source: {
          title: document.getElementById('evidenceTitle').value,
          url: document.getElementById('evidenceUrl').value,
          source_type: document.getElementById('evidenceSourceType').value,
          published_at: document.getElementById('evidenceDate').value,
          original_source_id: document.getElementById('evidenceOrigin').value,
          methodology_transparent: document.getElementById('evidenceMethodology').checked,
          position: document.getElementById('evidencePosition').value,
          data_type: document.getElementById('evidenceDataType').value,
        },
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Impossible d’ajouter cette source.');
    const assessments = currentEvidenceAssessments.map((item, index) => (
      Number(evidenceFinding.value) === index ? data.assessment : item
    ));
    renderEvidence(assessments);
    evidenceForm.reset();
  } catch (error) {
    evidenceFormError.textContent = error.message || 'Une erreur est survenue. Réessayez.';
  } finally {
    addEvidenceButton.disabled = false;
  }
});
