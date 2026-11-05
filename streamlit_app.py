import os
from datetime import UTC, date, datetime
from types import SimpleNamespace

import streamlit as st
from dotenv import load_dotenv
from streamlit.errors import StreamlitSecretNotFoundError
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

try:
    deployment_secrets = st.secrets.to_dict()
except (FileNotFoundError, StreamlitSecretNotFoundError):
    deployment_secrets = {}

for setting in (
    "DATABASE_URL",
    "SECRET_KEY",
    "AI_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "TAVILY_API_KEY",
):
    value = deployment_secrets.get(setting)
    if value:
        os.environ[setting] = str(value)

from app import (  # noqa: E402
    AIServiceError,
    EvidenceAssessment,
    EvidenceSource,
    Study,
    User,
    app as flask_app,
    build_reliability_score,
    build_report_evidence,
    clean_text,
    db,
    generate_market_report,
    parse_market_file,
    search_market_sources,
    validate_source,
)
from evidence import build_evidence_assessment


st.set_page_config(page_title="MarketRadar AI", page_icon="📊", layout="wide")

CRITERIA_LABELS = {
    "quality": "Qualité des sources · 30 %",
    "independence": "Sources indépendantes · 25 %",
    "freshness": "Fraîcheur des données · 25 %",
    "coherence": "Cohérence des informations · 20 %",
}
SOURCE_TYPES = {
    "government": "Organisme / statistique public",
    "academic": "Publication académique",
    "international_organization": "Organisation internationale",
    "industry_report": "Étude sectorielle",
    "company_primary": "Donnée primaire d’entreprise",
    "news": "Presse",
    "other": "Autre",
}
DATA_TYPES = {
    "price": "Prix · 7 jours",
    "market_trend": "Tendance de marché · 90 jours",
    "financial": "Donnée financière · 365 jours",
    "population": "Donnée démographique · 1 095 jours",
    "historical": "Donnée historique · 10 ans",
    "general": "Autre donnée · 180 jours",
}
POSITIONS = {
    "supports": "Confirme le constat",
    "contradicts": "Contredit le constat",
    "neutral": "Ne tranche pas",
}


def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _signup_form():
    st.subheader("Créer un compte")
    with st.form("signup_form"):
        email = st.text_input("Adresse e-mail").strip().lower()
        password = st.text_input("Mot de passe", type="password")
        confirm = st.text_input("Confirmer le mot de passe", type="password")
        submitted = st.form_submit_button("Créer mon compte", type="primary")
    if not submitted:
        return
    if not email or not password:
        st.error("L’adresse e-mail et le mot de passe sont obligatoires.")
        return
    if len(password) < 6:
        st.error("Le mot de passe doit contenir au moins 6 caractères.")
        return
    if password != confirm:
        st.error("Les deux mots de passe ne correspondent pas.")
        return
    with flask_app.app_context():
        if User.query.filter_by(email=email).first():
            st.error("Cette adresse e-mail est déjà utilisée.")
            return
        user = User(email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        st.session_state["user_id"] = user.id
        st.session_state["user_email"] = user.email
    _rerun()


def _login_form():
    st.subheader("Connexion")
    with st.form("login_form"):
        email = st.text_input("Adresse e-mail").strip().lower()
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", type="primary")
    if not submitted:
        return
    with flask_app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            st.error("Adresse e-mail ou mot de passe incorrect.")
            return
        st.session_state["user_id"] = user.id
        st.session_state["user_email"] = user.email
    _rerun()


def _render_authentication():
    st.write("Connecte-toi ou crée un compte pour préparer une étude de marché.")
    login_tab, signup_tab = st.tabs(["Connexion", "Créer un compte"])
    with login_tab:
        _login_form()
    with signup_tab:
        _signup_form()


def _generate_study(user_id, values, uploaded_file):
    dataset = None
    if uploaded_file is not None:
        if uploaded_file.size > 5 * 1024 * 1024:
            raise AIServiceError("Le fichier dépasse la limite de 5 Mo.", 400)
        upload = SimpleNamespace(filename=uploaded_file.name, read=uploaded_file.getvalue)
        dataset = parse_market_file(upload)
        values["dataset_context"] = dataset["context"]

    sources = search_market_sources(values)
    report = generate_market_report(values, sources)
    reliability = build_reliability_score(dataset)
    report.update({
        "reliability_score": reliability["score"],
        "reliability_label": reliability["label"],
        "reliability_factors": reliability["factors"],
        "reliability_disclaimer": reliability["disclaimer"],
    })
    if dataset:
        report["uploaded_data"] = {
            "filename": dataset["filename"],
            "row_count": dataset["row_count"],
            "column_count": dataset["column_count"],
            "truncated": dataset["truncated"],
        }

    assessments, cited_sources = build_report_evidence(report, sources)
    report.pop("finding_evidence", None)
    report["evidence_assessments"] = assessments
    report["sources"] = [f"{source['title']} — {source['url']}" for source in cited_sources]
    if not os.environ.get("TAVILY_API_KEY", "").strip():
        report["evidence_search_status"] = "not_configured"
        report["evidence_search_message"] = (
            "Recherche Web indisponible : configure TAVILY_API_KEY dans les secrets Streamlit. "
            "Aucune source ni aucun score n’a été inventé."
        )
    elif not sources:
        report["evidence_search_status"] = "no_results"
        report["evidence_search_message"] = (
            "La recherche Web n’a renvoyé aucune source exploitable; les constats restent sans score."
        )
    elif not cited_sources:
        report["evidence_search_status"] = "no_citations"
        report["evidence_search_message"] = (
            "Aucun résultat Web n’a été retenu pour étayer les constats; les scores restent insuffisants."
        )
    else:
        report["evidence_search_status"] = "searched"
        report["evidence_search_message"] = (
            f"{len(cited_sources)} résultat(s) Web cité(s). Les extraits et dates proviennent de Tavily; "
            "vérifie les pages avant toute décision."
        )

    study = Study(
        company=values.get("company"),
        market=clean_text(values.get("market"), "Marché inconnu"),
        country=clean_text(values.get("country"), "Monde"),
        question=clean_text(values.get("question"), "Question non renseignée"),
        objective=clean_text(values.get("objective"), "Objectif non renseigné"),
        report=report,
        user_id=user_id,
    )
    db.session.add(study)
    db.session.flush()
    for finding_index, assessment in enumerate(assessments):
        for source in assessment["sources"]:
            db.session.add(EvidenceSource(
                study_id=study.id,
                finding_index=finding_index,
                title=source["title"],
                url=source["url"],
                source_type=source["source_type"],
                published_at=date.fromisoformat(source["published_at"]) if source["published_at"] else None,
                original_source_id=source["original_source_id"],
                methodology_transparent=source["methodology_transparent"],
                position=source["position"],
                data_type=source["data_type"],
            ))
        db.session.add(EvidenceAssessment(
            study_id=study.id,
            finding_index=finding_index,
            conclusion=assessment["conclusion"],
            score=assessment["score"],
            status=assessment["status"],
            criteria=assessment["criteria"],
            warnings=assessment["warnings"],
            explanation=assessment["explanation"],
        ))
    db.session.commit()
    report["study_id"] = study.id
    return report, study.id


def _render_study_form(user_id):
    st.header("Nouvelle étude de marché")
    with st.form("study_form"):
        company = st.text_input("Entreprise", value="NovaGrowth")
        country = st.text_input("Pays ou zone", value="France")
        market = st.text_input("Marché à étudier", value="IA B2B pour PME")
        question = st.text_area(
            "Votre question métier",
            value="Quel est le potentiel de développement d’une solution d’IA pour améliorer la productivité des PME en France ?",
        )
        objective = st.text_input(
            "Objectif stratégique (optionnel)",
            value="Évaluer la demande et préparer le lancement d’une offre premium pour les PME.",
        )
        uploaded_file = st.file_uploader(
            "Données à analyser (optionnel)",
            type=["csv", "xlsx"],
            help="Maximum 5 Mo. L’échantillon sera envoyé au fournisseur IA configuré.",
        )
        submitted = st.form_submit_button("Rechercher et générer l’étude", type="primary")
    if not submitted:
        return
    if not market.strip() or not country.strip() or not question.strip():
        st.error("Renseigne le marché, le pays et la question métier.")
        return
    values = {
        "company": company,
        "country": country,
        "market": market,
        "question": question,
        "objective": objective,
    }
    try:
        with st.spinner("Recherche Web et génération de l’étude en cours…"):
            with flask_app.app_context():
                report, study_id = _generate_study(user_id, values, uploaded_file)
        st.session_state["active_study_id"] = study_id
        st.session_state["active_report"] = report
        _rerun()
    except AIServiceError as error:
        st.error(str(error))


def _format_score(score):
    return "Données insuffisantes" if score is None else f"{score:g}/100"


def _render_evidence(report, study_id):
    st.subheader("Evidence Score · solidité des preuves")
    st.caption(
        "Méthode initiale à tester et calibrer, non scientifiquement validée. "
        "Les résultats Web sont évalués à partir des extraits; ouvre les liens et vérifie-les."
    )
    if report.get("evidence_search_message"):
        if report.get("evidence_search_status") == "searched":
            st.info(report["evidence_search_message"])
        else:
            st.warning(report["evidence_search_message"])

    assessments = report.get("evidence_assessments", [])
    for index, assessment in enumerate(assessments):
        with st.container(border=True):
            st.markdown(f"**Constat {index + 1} :** {assessment['conclusion']}")
            st.metric("Evidence Score", _format_score(assessment["score"]))
            if assessment["score"] is not None:
                st.progress(max(0.0, min(1.0, float(assessment["score"]) / 100)))
            for key, criterion in assessment["criteria"].items():
                contribution = criterion["contribution"]
                result = (
                    "Données insuffisantes"
                    if criterion["score"] is None
                    else f"{criterion['score']:.1f}/100 · contribution {contribution:.1f}"
                )
                st.write(f"**{CRITERIA_LABELS[key]} :** {result}")
            st.write(assessment["explanation"])
            for warning in assessment.get("warnings", []):
                st.warning(warning)
            st.markdown("**Sources utilisées**")
            if assessment.get("sources"):
                for source in assessment["sources"]:
                    published = source.get("published_at") or "date non fournie"
                    st.markdown(
                        f"- [{source['title']}]({source['url']}) · "
                        f"{SOURCE_TYPES.get(source['source_type'], source['source_type'])} · {published}"
                    )
            else:
                st.caption("Aucune source retenue pour ce constat.")

    if not assessments:
        return
    st.markdown("#### Ajouter une source manuellement")
    with st.form(f"manual_source_{study_id}"):
        finding_index = st.selectbox(
            "Constat concerné",
            options=range(len(assessments)),
            format_func=lambda value: assessments[value]["conclusion"],
        )
        title = st.text_input("Titre de la source")
        url = st.text_input("URL", placeholder="https://…")
        source_type = st.selectbox(
            "Type de source",
            options=list(SOURCE_TYPES),
            format_func=lambda value: SOURCE_TYPES[value],
        )
        published_at = st.date_input("Date de publication (si connue)", value=None)
        origin = st.text_input("Origine originale", help="Utilise la même origine pour les reprises d’un même rapport.")
        data_type = st.selectbox(
            "Type de donnée",
            options=list(DATA_TYPES),
            format_func=lambda value: DATA_TYPES[value],
        )
        position = st.selectbox(
            "Position par rapport au constat",
            options=list(POSITIONS),
            format_func=lambda value: POSITIONS[value],
        )
        methodology_transparent = st.checkbox("La méthodologie est transparente et documentée")
        submitted = st.form_submit_button("Ajouter la source et recalculer")
    if not submitted:
        return

    source_data = {
        "title": title,
        "url": url,
        "source_type": source_type,
        "published_at": published_at.isoformat() if published_at else None,
        "original_source_id": origin,
        "methodology_transparent": methodology_transparent,
        "position": position,
        "data_type": data_type,
    }
    try:
        source_data = validate_source(source_data)
        with flask_app.app_context():
            study = Study.query.filter_by(id=study_id, user_id=user_id).first()
            if not study:
                st.error("Étude introuvable.")
                return
            db.session.add(EvidenceSource(
                study_id=study.id,
                finding_index=finding_index,
                title=source_data["title"],
                url=source_data["url"],
                source_type=source_data["source_type"],
                published_at=date.fromisoformat(source_data["published_at"]) if source_data["published_at"] else None,
                original_source_id=source_data["original_source_id"],
                methodology_transparent=source_data["methodology_transparent"],
                position=source_data["position"],
                data_type=source_data["data_type"],
            ))
            db.session.flush()
            sources = EvidenceSource.query.filter_by(
                study_id=study.id,
                finding_index=finding_index,
            ).order_by(EvidenceSource.id).all()
            assessment = build_evidence_assessment(
                assessments[finding_index]["conclusion"],
                [{
                    "title": item.title,
                    "url": item.url,
                    "source_type": item.source_type,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "original_source_id": item.original_source_id,
                    "methodology_transparent": item.methodology_transparent,
                    "position": item.position,
                    "data_type": item.data_type,
                } for item in sources],
            )
            db_assessment = EvidenceAssessment.query.filter_by(
                study_id=study.id,
                finding_index=finding_index,
            ).first()
            if not db_assessment:
                db_assessment = EvidenceAssessment(
                    study_id=study.id,
                    finding_index=finding_index,
                    conclusion=assessment["conclusion"],
                )
                db.session.add(db_assessment)
            db_assessment.score = assessment["score"]
            db_assessment.status = assessment["status"]
            db_assessment.criteria = assessment["criteria"]
            db_assessment.warnings = assessment["warnings"]
            db_assessment.explanation = assessment["explanation"]
            db_assessment.calculated_at = datetime.now(UTC)
            report = dict(study.report or {})
            saved_assessments = list(report.get("evidence_assessments") or [])
            saved_assessments[finding_index] = assessment
            report["evidence_assessments"] = saved_assessments
            study.report = report
            db.session.commit()
        st.session_state["active_report"] = report
        st.success("Source enregistrée et score recalculé.")
        _rerun()
    except ValueError as error:
        st.error(str(error))


def _render_report(report, study_id):
    st.title(report.get("title", "Étude de marché"))
    st.caption(
        f"{report.get('market', '')} · {report.get('country', '')} · "
        f"{report.get('company', 'Entreprise non précisée')}"
    )
    with st.container(border=True):
        st.caption("INDICE INDICATIF DE COUVERTURE DES DONNÉES — différent de l’Evidence Score")
        st.metric(
            f"Couverture · {report.get('reliability_label', 'N/A')}",
            f"{report.get('reliability_score', '—')}/100",
        )
        st.write(report.get("reliability_disclaimer", ""))
    st.subheader("Synthèse exécutive")
    st.write(report.get("executive_summary", ""))
    _render_evidence(report, study_id)
    left, right = st.columns(2)
    with left:
        st.subheader("Recommandations")
        for item in report.get("recommendations", []):
            st.markdown(f"- {item}")
    with right:
        st.subheader("Indicateurs")
        for insight in report.get("insights", []):
            st.markdown(f"**{insight['title']} — {insight['value']}**")
            st.write(insight["description"])
    st.subheader("Plan d’étude")
    for step in report.get("study_plan", []):
        st.markdown(f"**{step['title']}** — {step['description']}")


def main():
    if "user_id" not in st.session_state:
        st.title("MarketRadar AI")
        _render_authentication()
        return
    st.title("MarketRadar AI")

    user_id = st.session_state["user_id"]
    with st.sidebar:
        st.write(f"Connecté : **{st.session_state.get('user_email', '')}**")
        if st.button("Se déconnecter"):
            for key in ("user_id", "user_email", "active_study_id", "active_report"):
                st.session_state.pop(key, None)
            _rerun()

        with flask_app.app_context():
            studies = Study.query.filter_by(user_id=user_id).order_by(Study.created_at.desc()).limit(50).all()
            study_options = {study.id: f"{study.market} · {study.created_at.strftime('%d/%m/%Y')}" for study in studies}
        if study_options:
            selected = st.selectbox(
                "Mes études enregistrées",
                options=list(study_options),
                format_func=lambda value: study_options[value],
            )
            if st.button("Ouvrir cette étude"):
                with flask_app.app_context():
                    study = Study.query.filter_by(id=selected, user_id=user_id).first()
                    if study:
                        st.session_state["active_study_id"] = study.id
                        st.session_state["active_report"] = dict(study.report or {})
                        st.session_state["active_report"]["study_id"] = study.id
                _rerun()

    if not os.environ.get("DATABASE_URL"):
        st.warning(
            "La base de données utilise SQLite local. Sur Streamlit Community Cloud, les données peuvent "
            "être perdues lors d’un redéploiement ou d’une mise en veille. Configure une base PostgreSQL "
            "persistante dans les secrets Streamlit pour conserver les comptes et études."
        )
    if not os.environ.get("TAVILY_API_KEY"):
        st.info("Ajoute TAVILY_API_KEY dans les secrets Streamlit pour activer la recherche Web automatique.")

    _render_study_form(user_id)
    report = st.session_state.get("active_report")
    study_id = st.session_state.get("active_study_id")
    if report and study_id:
        st.divider()
        _render_report(report, study_id)


if __name__ == "__main__":
    main()
