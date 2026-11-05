from datetime import date
from urllib.parse import urlsplit


WEIGHTS = {"quality": 0.30, "independence": 0.25, "freshness": 0.25, "coherence": 0.20}
SOURCE_AUTHORITY = {
    "government": 95,
    "academic": 90,
    "international_organization": 90,
    "industry_report": 75,
    "company_primary": 70,
    "news": 60,
    "other": 35,
}
SOURCE_TYPES = set(SOURCE_AUTHORITY)
POSITIONS = {"supports", "contradicts", "neutral"}
DATA_VALIDITY_DAYS = {
    "price": 7,
    "market_trend": 90,
    "financial": 365,
    "population": 1095,
    "historical": 3650,
    "general": 180,
}


def calculate_weighted_score(quality, independence, freshness, coherence):
    """Apply the initial, configurable-in-code weighting proposal."""
    values = (quality, independence, freshness, coherence)
    if any(not isinstance(value, (int, float)) or not 0 <= value <= 100 for value in values):
        raise ValueError("Chaque critère doit être compris entre 0 et 100.")
    return round(sum(value * weight for value, weight in zip(values, WEIGHTS.values())), 1)


def validate_source(source):
    required = ("title", "url", "source_type", "original_source_id", "position", "data_type")
    if not isinstance(source, dict) or any(
        not isinstance(source.get(key), str) or not source[key].strip()
        for key in required
    ):
        raise ValueError("Renseignez tous les champs obligatoires de la source.")
    if source["source_type"].strip() not in SOURCE_TYPES:
        raise ValueError("Type de source non reconnu.")
    if source["position"].strip() not in POSITIONS:
        raise ValueError("Position de la source non reconnue.")
    if source["data_type"].strip() not in DATA_VALIDITY_DAYS:
        raise ValueError("Type de donnée non reconnu.")
    try:
        parsed_url = urlsplit(source["url"].strip())
    except ValueError as error:
        raise ValueError("L’URL de la source est invalide.") from error
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or parsed_url.username or parsed_url.password:
        raise ValueError("L’URL doit commencer par http:// ou https://.")
    published_at = source.get("published_at")
    if published_at:
        if not isinstance(published_at, str):
            raise ValueError("La date de publication doit être au format AAAA-MM-JJ.")
        try:
            parsed_date = date.fromisoformat(published_at)
        except ValueError as error:
            raise ValueError("La date de publication doit être au format AAAA-MM-JJ.") from error
        if parsed_date.isoformat() != published_at:
            raise ValueError("La date de publication doit être au format AAAA-MM-JJ.")
    if not isinstance(source.get("methodology_transparent"), bool):
        raise ValueError("Indiquez si la méthodologie de la source est transparente.")
    return {
        **source,
        "title": source["title"].strip()[:300],
        "url": source["url"].strip()[:2000],
        "source_type": source["source_type"].strip(),
        "published_at": published_at or None,
        "position": source["position"].strip(),
        "data_type": source["data_type"].strip(),
        "original_source_id": source["original_source_id"].strip().casefold()[:300],
    }


def _freshness_score(source, today):
    if not source["published_at"]:
        return 0, f"Date de publication indisponible : {source['title']}."
    published = date.fromisoformat(source["published_at"])
    age_days = (today - published).days
    validity_days = DATA_VALIDITY_DAYS[source["data_type"]]
    if age_days < 0:
        return 0, f"Date future à vérifier : {source['title']}."
    score = round(max(0, 100 * (1 - age_days / validity_days)), 1)
    if age_days > validity_days:
        return score, f"Source obsolète pour le type « {source['data_type']} » : {source['title']}."
    return score, None


def build_evidence_assessment(conclusion, sources, today=None):
    """Compute an assessment from explicitly supplied, validated source metadata."""
    today = today or date.today()
    sources = [validate_source(source) for source in sources]
    warnings = []
    if not sources:
        return {
            "conclusion": conclusion,
            "score": None,
            "status": "insufficient",
            "criteria": {key: {"score": None, "weight": weight, "contribution": None} for key, weight in WEIGHTS.items()},
            "sources": [],
            "warnings": ["Aucune source documentée pour ce constat."],
            "explanation": "Ajoutez des sources vérifiées et leur position avant d’interpréter un score.",
            "weights": WEIGHTS,
        }

    independent_sources_by_id = {}
    for source in sources:
        independent_sources_by_id.setdefault(source["original_source_id"], source)
    independent_sources = list(independent_sources_by_id.values())
    independent_count = len(independent_sources)
    independence = min(100, independent_count * 25)
    quality_scores = [
        SOURCE_AUTHORITY[source["source_type"]] * 0.7
        + (30 if source["methodology_transparent"] else 0)
        for source in independent_sources
    ]
    quality = round(sum(quality_scores) / len(quality_scores), 1)
    freshness_scores = []
    for source in independent_sources:
        freshness, warning = _freshness_score(source, today)
        freshness_scores.append(freshness)
        if warning:
            warnings.append(warning)

    directional = [source for source in independent_sources if source["position"] != "neutral"]
    if directional:
        positions = [source["position"] for source in directional]
        coherence = round(100 * max(positions.count("supports"), positions.count("contradicts")) / len(positions), 1)
    else:
        coherence = 0
        warnings.append("Aucune source ne confirme ni ne contredit explicitement le constat.")
    key_positions = {
        source["position"]
        for source in independent_sources
        if SOURCE_AUTHORITY[source["source_type"]] >= 70 and source["position"] != "neutral"
    }
    if len(key_positions) > 1:
        warnings.append("Des sources importantes se contredisent : vérifiez leurs périmètres et méthodologies.")

    freshness = round(sum(freshness_scores) / len(freshness_scores), 1)
    scores = {
        "quality": quality,
        "independence": independence,
        "freshness": freshness,
        "coherence": coherence,
    }
    criteria = {
        key: {"score": value, "weight": WEIGHTS[key], "contribution": round(value * WEIGHTS[key], 1)}
        for key, value in scores.items()
    }
    sufficient = independent_count >= 2 and bool(directional)
    score = calculate_weighted_score(**scores) if sufficient else None
    if independent_count < 2:
        warnings.append(f"Sources indépendantes insuffisantes : {independent_count} sur 2 minimum.")
    explanation = (
        "Le score combine qualité (autorité du type de source et transparence méthodologique), "
        "indépendance (origine déclarée), fraîcheur (durée adaptée au type de donnée) et cohérence "
        "(accord des positions déclarées)."
    )
    if not sufficient:
        explanation = "Données insuffisantes pour un score final. " + explanation
    return {
        "conclusion": conclusion,
        "score": score,
        "status": "scored" if sufficient else "insufficient",
        "criteria": criteria,
        "sources": sources,
        "warnings": list(dict.fromkeys(warnings)),
        "explanation": explanation,
        "weights": WEIGHTS,
    }
