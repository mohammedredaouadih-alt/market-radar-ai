import json
import os
from datetime import date
from io import BytesIO

os.environ['DATABASE_URL'] = 'sqlite://'

import app as app_module
from app import app, db
from app import EvidenceAssessment, EvidenceSource, Study, User
from evidence import build_evidence_assessment, calculate_weighted_score


def setup_function():
    os.environ.pop('TAVILY_API_KEY', None)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        assert str(db.engine.url) == 'sqlite://'
        db.drop_all()
        db.create_all()


def test_login_page_loads():
    client = app.test_client()
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Connexion' in response.data or b'login' in response.data.lower()


def test_user_can_signup_and_login():
    client = app.test_client()
    signup = client.post('/signup', data={
        'email': 'test@example.com',
        'password': 'secret123'
    }, follow_redirects=True)
    assert signup.status_code == 200

    login = client.post('/login', data={
        'email': 'test@example.com',
        'password': 'secret123'
    }, follow_redirects=True)
    assert login.status_code == 200
    assert b'Se d' in login.data


def test_analyze_route_requires_auth():
    client = app.test_client()
    response = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?',
        'objective': 'Lancer un produit'
    })
    assert response.status_code == 401


def test_analysis_requires_openai_key(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    client = app.test_client()
    client.post('/signup', data={'email': 'user2@example.com', 'password': 'secret123'}, follow_redirects=True)

    response = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?',
        'objective': 'Lancer un produit'
    })

    assert response.status_code == 503
    assert 'OPENAI_API_KEY' in response.get_json()['error']


def test_analysis_uses_openai_and_saves_report(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'user3@example.com', 'password': 'secret123'}, follow_redirects=True)

    report = {
        'title': 'Potentiel du marché IA B2B',
        'executive_summary': 'Résumé généré par le modèle.',
        'key_findings': ['Premier constat'],
        'insights': [{'title': 'Demande', 'value': 'À valider', 'description': 'Indicateur à rechercher.'}],
        'study_plan': [{'title': 'Cadrage', 'description': 'Définir le périmètre.'}],
        'recommendations': ['Interroger des clients potentiels.'],
        'sources': ['INSEE, données sectorielles à consulter'],
    }
    captured = {}

    class ProviderResponse:
        status_code = 200

        def json(self):
            return {'choices': [{'message': {'content': json.dumps(report)}}]}

    def fake_openai_request(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return ProviderResponse()

    monkeypatch.setattr(app_module.requests, 'post', fake_openai_request)
    response = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?',
        'objective': 'Lancer un produit'
    })

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ai_enabled'] is True
    assert payload['title'] == report['title']
    assert captured['url'] == 'https://api.openai.com/v1/chat/completions'
    assert captured['headers']['Authorization'] == 'Bearer test-api-key'
    assert captured['payload']['response_format']['type'] == 'json_schema'
    with app.app_context():
        assert Study.query.count() == 1


def test_openai_quota_error_explains_billing(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'quota@example.com', 'password': 'secret123'}, follow_redirects=True)

    class QuotaResponse:
        status_code = 429

        def json(self):
            return {'error': {'code': 'insufficient_quota', 'type': 'insufficient_quota'}}

    monkeypatch.setattr(app_module.requests, 'post', lambda *args, **kwargs: QuotaResponse())
    response = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?'
    })

    assert response.status_code == 503
    assert 'facturation' in response.get_json()['error']


def test_openai_rate_limit_error_suggests_retry(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'limit@example.com', 'password': 'secret123'}, follow_redirects=True)

    class RateLimitResponse:
        status_code = 429

        def json(self):
            return {'error': {'code': 'rate_limit_exceeded', 'type': 'requests'}}

    monkeypatch.setattr(app_module.requests, 'post', lambda *args, **kwargs: RateLimitResponse())
    response = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?'
    })

    assert response.status_code == 503
    assert 'Attendez un peu' in response.get_json()['error']


def test_analysis_uses_gemini_and_saves_report(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.8-flash')
    client = app.test_client()
    client.post('/signup', data={'email': 'gemini@example.com', 'password': 'secret123'}, follow_redirects=True)

    report = {
        'title': 'Étude Gemini',
        'executive_summary': 'Résumé généré par Gemini.',
        'key_findings': ['Constat à vérifier'],
        'insights': [{'title': 'Demande', 'value': 'Moyenne', 'description': 'À confirmer par des données.'}],
        'study_plan': [{'title': 'Cadrage', 'description': 'Délimiter le marché.'}],
        'recommendations': ['Tester le segment auprès de clients.'],
        'sources': ['Données publiques à consulter'],
    }
    captured = {}

    class GeminiResponse:
        status_code = 200

        def json(self):
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(report)}]}}]}

    def fake_gemini_request(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return GeminiResponse()

    monkeypatch.setattr(app_module.requests, 'post', fake_gemini_request)
    response = client.post('/api/analyze', json={
        'market': 'Logiciels B2B',
        'country': 'France',
        'question': 'Quel segment viser ?'
    })

    assert response.status_code == 200
    assert response.get_json()['ai_enabled'] is True
    assert response.get_json()['title'] == report['title']
    assert captured['url'] == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent'
    assert captured['headers']['x-goog-api-key'] == 'test-gemini-key'
    assert captured['payload']['generationConfig']['responseMimeType'] == 'application/json'


def test_analysis_accepts_csv_and_returns_reliability_score(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'csv@example.com', 'password': 'secret123'}, follow_redirects=True)
    report = {
        'title': 'Étude avec données',
        'executive_summary': 'Résumé.',
        'key_findings': [],
        'insights': [],
        'study_plan': [],
        'recommendations': [],
        'sources': [],
    }
    captured = {}

    class ProviderResponse:
        status_code = 200

        def json(self):
            return {'choices': [{'message': {'content': json.dumps(report)}}]}

    def fake_openai_request(url, headers, json, timeout):
        captured.update(payload=json)
        return ProviderResponse()

    monkeypatch.setattr(app_module.requests, 'post', fake_openai_request)
    csv_content = 'segment,pays,clients\n' + ''.join(f'Segment {i},France,{i * 10}\n' for i in range(1, 12))
    response = client.post('/api/analyze', data={
        'market': 'Logiciels B2B',
        'country': 'France',
        'question': 'Quel segment viser ?',
        'data_file': (BytesIO(csv_content.encode('utf-8')), 'donnees.csv'),
    }, content_type='multipart/form-data')

    assert response.status_code == 200
    result = response.get_json()
    assert result['reliability_score'] == 75
    assert result['reliability_label'] == 'Bonne'
    assert result['uploaded_data'] == {
        'filename': 'donnees.csv',
        'row_count': 11,
        'column_count': 3,
        'truncated': False,
    }
    assert 'Segment 1' in captured['payload']['messages'][1]['content']
    assert result['reliability_disclaimer']


def test_analysis_rejects_unsupported_file_type():
    client = app.test_client()
    client.post('/signup', data={'email': 'badfile@example.com', 'password': 'secret123'}, follow_redirects=True)

    response = client.post('/api/analyze', data={
        'market': 'Logiciels B2B',
        'country': 'France',
        'question': 'Quel segment viser ?',
        'data_file': (BytesIO(b'not excel'), 'donnees.xls'),
    }, content_type='multipart/form-data')

    assert response.status_code == 400
    assert 'CSV ou Excel' in response.get_json()['error']


def test_analysis_rejects_files_over_size_limit():
    client = app.test_client()
    client.post('/signup', data={'email': 'oversize@example.com', 'password': 'secret123'}, follow_redirects=True)

    response = client.post('/api/analyze', data={
        'market': 'Logiciels B2B',
        'country': 'France',
        'question': 'Quel segment viser ?',
        'data_file': (BytesIO(b'x' * (5 * 1024 * 1024 + 1)), 'donnees.csv'),
    }, content_type='multipart/form-data')

    assert response.status_code == 413
    assert '5 Mo' in response.get_json()['error']


def test_parse_excel_file():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['Segment', 'Pays', 'Clients'])
    sheet.append(['PME', 'France', 120])
    content = BytesIO()
    workbook.save(content)
    content.seek(0)

    parsed = app_module.parse_market_file(type('Upload', (), {
        'filename': 'donnees.xlsx',
        'read': content.read,
    })())

    assert parsed['row_count'] == 1
    assert parsed['column_count'] == 3
    assert 'PME' in parsed['context']


def test_analysis_without_file_has_baseline_reliability(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'baseline@example.com', 'password': 'secret123'}, follow_redirects=True)

    class ProviderResponse:
        status_code = 200

        def json(self):
            return {'choices': [{'message': {'content': json.dumps({
                'title': 'Étude sans fichier',
                'executive_summary': 'Résumé.',
                'key_findings': [],
                'insights': [],
                'study_plan': [],
                'recommendations': [],
                'sources': [],
            })}}]}

    monkeypatch.setattr(app_module.requests, 'post', lambda *args, **kwargs: ProviderResponse())
    response = client.post('/api/analyze', json={
        'market': 'Logiciels B2B',
        'country': 'France',
        'question': 'Quel segment viser ?',
    })

    assert response.status_code == 200
    assert response.get_json()['reliability_score'] == 30


def evidence_source(title, origin, position='supports', published_at='2026-10-01', **overrides):
    source = {
        'title': title,
        'url': f'https://example.org/{title.replace(" ", "-")}',
        'source_type': 'government',
        'published_at': published_at,
        'original_source_id': origin,
        'methodology_transparent': True,
        'position': position,
        'data_type': 'general',
    }
    source.update(overrides)
    return source


def test_evidence_weighting_example_and_bounds():
    assert calculate_weighted_score(90, 80, 70, 60) == 76.5
    assert calculate_weighted_score(0, 0, 0, 0) == 0
    assert calculate_weighted_score(100, 100, 100, 100) == 100


def test_evidence_score_requires_two_independent_sources():
    assessment = build_evidence_assessment(
        'Le marché progresse.',
        [evidence_source('Source A', 'rapport-original')],
        today=date(2026, 10, 28),
    )
    assert assessment['score'] is None
    assert assessment['status'] == 'insufficient'
    assert assessment['criteria']['quality']['score'] > 0
    assert any('insuffisantes' in warning for warning in assessment['warnings'])


def test_evidence_deduplicates_republished_sources():
    assessment = build_evidence_assessment(
        'Le marché progresse.',
        [
            evidence_source('Article A', 'meme-rapport'),
            evidence_source('Article B', 'Meme-Rapport'),
        ],
        today=date(2026, 10, 28),
    )
    assert assessment['score'] is None
    assert assessment['criteria']['independence']['score'] == 25


def test_evidence_missing_publication_date_gets_zero_freshness_and_warning():
    assessment = build_evidence_assessment(
        'La demande progresse.',
        [
            evidence_source('Source A', 'source-a', published_at=''),
            evidence_source('Source B', 'source-b', published_at=''),
        ],
        today=date(2026, 10, 28),
    )
    assert assessment['score'] is not None
    assert assessment['criteria']['freshness']['score'] == 0
    assert any('Date de publication indisponible' in warning for warning in assessment['warnings'])


def test_evidence_warns_about_conflicts_and_stale_price_data():
    assessment = build_evidence_assessment(
        'Le prix augmente.',
        [
            evidence_source('Source A', 'source-a', published_at='2026-10-01', data_type='price'),
            evidence_source(
                'Source B',
                'source-b',
                position='contradicts',
                published_at='2026-10-01',
                data_type='price',
            ),
        ],
        today=date(2026, 10, 28),
    )
    assert assessment['score'] is not None
    assert assessment['criteria']['coherence']['score'] == 50
    assert any('contredisent' in warning for warning in assessment['warnings'])
    assert any('obsolète' in warning for warning in assessment['warnings'])


def test_analysis_persists_empty_evidence_assessment(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'evidence@example.com', 'password': 'secret123'}, follow_redirects=True)

    report = {
        'title': 'Étude avec constat',
        'executive_summary': 'Résumé.',
        'key_findings': ['La demande doit être vérifiée.'],
        'insights': [],
        'study_plan': [],
        'recommendations': [],
        'sources': ['Organisme à consulter'],
    }

    class ProviderResponse:
        status_code = 200

        def json(self):
            return {'choices': [{'message': {'content': json.dumps(report)}}]}

    monkeypatch.setattr(app_module.requests, 'post', lambda *args, **kwargs: ProviderResponse())
    response = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?',
    })
    payload = response.get_json()
    assert payload['evidence_assessments'][0]['score'] is None
    assert payload['evidence_assessments'][0]['status'] == 'insufficient'
    with app.app_context():
        assert EvidenceAssessment.query.count() == 1
        assert EvidenceAssessment.query.first().score is None


def test_evidence_route_recalculates_and_persists_server_score(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'evidence2@example.com', 'password': 'secret123'}, follow_redirects=True)
    report = {
        'title': 'Étude',
        'executive_summary': 'Résumé.',
        'key_findings': ['La demande progresse.'],
        'insights': [],
        'study_plan': [],
        'recommendations': [],
        'sources': [],
    }

    class ProviderResponse:
        status_code = 200

        def json(self):
            return {'choices': [{'message': {'content': json.dumps(report)}}]}

    monkeypatch.setattr(app_module.requests, 'post', lambda *args, **kwargs: ProviderResponse())
    study_id = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?',
    }).get_json()['study_id']

    first = evidence_source('Source A', 'source-a', published_at=date.today().isoformat())
    second = evidence_source('Source B', 'source-b', published_at=date.today().isoformat())
    client.post(f'/api/studies/{study_id}/evidence', json={'finding_index': 0, 'source': first})
    response = client.post(f'/api/studies/{study_id}/evidence', json={
        'finding_index': 0,
        'source': second,
        'score': 100,
    })
    result = response.get_json()['assessment']
    assert response.status_code == 200
    expected_score = calculate_weighted_score(**{
        name: criterion['score']
        for name, criterion in result['criteria'].items()
    })
    assert result['score'] == expected_score
    assert result['score'] < 100
    with app.app_context():
        assert EvidenceSource.query.count() == 2
        assert EvidenceAssessment.query.first().score == result['score']


def test_tavily_search_uses_configured_key_and_only_returns_real_results(monkeypatch):
    monkeypatch.setenv('TAVILY_API_KEY', 'tavily-test-key')
    captured = {}

    class TavilyResponse:
        status_code = 200

        def json(self):
            return {'results': [
                {
                    'title': 'Statistiques officielles',
                    'url': 'https://data.gouv.fr/datasets/example',
                    'content': 'Données publiées par un organisme public.',
                    'published_date': '2026-10-25T10:00:00Z',
                },
                {'title': 'Résultat sans URL', 'content': 'Ignorer ce résultat.'},
                {
                    'title': 'Source sans date',
                    'url': 'https://example.org/report',
                    'content': 'Extrait vérifiable.',
                },
            ]}

    def fake_search(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return TavilyResponse()

    monkeypatch.setattr(app_module.requests, 'post', fake_search)
    results = app_module.search_market_sources({
        'market': 'Logiciels B2B',
        'country': 'France',
        'question': 'Quel segment viser ?',
        'objective': 'Lancer une offre',
    })
    assert captured['url'] == 'https://api.tavily.com/search'
    assert captured['headers']['Authorization'] == 'Bearer tavily-test-key'
    assert 'France' in captured['payload']['query']
    assert len(results) == 2
    assert results[0]['source_type'] == 'government'
    assert results[0]['published_at'] == '2026-10-25'
    assert results[1]['published_at'] is None


def test_analysis_cites_tavily_results_and_persists_automatic_evidence(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-api-key')
    monkeypatch.setenv('TAVILY_API_KEY', 'tavily-test-key')
    client = app.test_client()
    client.post('/signup', data={'email': 'auto-evidence@example.com', 'password': 'secret123'}, follow_redirects=True)
    sources = [
        {
            'source_id': '0',
            'title': 'Source publique',
            'url': 'https://data.gouv.fr/report',
            'source_type': 'government',
            'published_at': date.today().isoformat(),
            'original_source_id': 'data.gouv.fr',
            'methodology_transparent': False,
            'position': 'neutral',
            'data_type': 'general',
            'content': 'Premier extrait indépendant.',
        },
        {
            'source_id': '1',
            'title': 'Source internationale',
            'url': 'https://oecd.org/report',
            'source_type': 'international_organization',
            'published_at': date.today().isoformat(),
            'original_source_id': 'oecd.org',
            'methodology_transparent': False,
            'position': 'neutral',
            'data_type': 'general',
            'content': 'Second extrait indépendant.',
        },
    ]
    monkeypatch.setattr(app_module, 'search_market_sources', lambda _data: sources)
    report = {
        'title': 'Étude sourcée',
        'executive_summary': 'Résumé.',
        'key_findings': ['La demande progresse.'],
        'insights': [],
        'study_plan': [],
        'recommendations': [],
        'sources': [],
        'finding_evidence': [{
            'finding_index': '0',
            'sources': [
                {'source_index': '0', 'position': 'supports', 'data_type': 'market_trend', 'methodology_transparent': True},
                {'source_index': '1', 'position': 'supports', 'data_type': 'market_trend', 'methodology_transparent': True},
            ],
        }],
    }
    captured = {}

    class ProviderResponse:
        status_code = 200

        def json(self):
            return {'choices': [{'message': {'content': json.dumps(report)}}]}

    def fake_openai_request(url, headers, json, timeout):
        captured.update(url=url, payload=json)
        return ProviderResponse()

    monkeypatch.setattr(app_module.requests, 'post', fake_openai_request)
    response = client.post('/api/analyze', json={
        'market': 'IA B2B',
        'country': 'France',
        'question': 'Quel potentiel ?',
    })
    result = response.get_json()
    assert response.status_code == 200
    assert result['evidence_search_status'] == 'searched'
    assert result['evidence_assessments'][0]['score'] is not None
    assert result['sources'] == [
        'Source publique — https://data.gouv.fr/report',
        'Source internationale — https://oecd.org/report',
    ]
    assert 'Premier extrait indépendant.' in captured['payload']['messages'][1]['content']
    with app.app_context():
        assert EvidenceSource.query.count() == 2


def test_evidence_route_rejects_invalid_metadata_and_other_users():
    client = app.test_client()
    client.post('/signup', data={'email': 'evidence3@example.com', 'password': 'secret123'}, follow_redirects=True)
    with app.app_context():
        owner = User.query.filter_by(email='evidence3@example.com').first()
        study = Study(
            market='IA B2B',
            country='France',
            question='Quel potentiel ?',
            objective='',
            report={'key_findings': ['Constat à vérifier.']},
            user_id=owner.id,
        )
        db.session.add(study)
        db.session.commit()
        study_id = study.id

    invalid = client.post(f'/api/studies/{study_id}/evidence', json={
        'finding_index': 0,
        'source': {},
    })
    assert invalid.status_code == 400
    client.get('/logout')
    client.post('/signup', data={'email': 'evidence4@example.com', 'password': 'secret123'}, follow_redirects=True)
    forbidden = client.post(f'/api/studies/{study_id}/evidence', json={
        'finding_index': 0,
        'source': evidence_source('Source', 'source'),
    })
    assert forbidden.status_code == 404
