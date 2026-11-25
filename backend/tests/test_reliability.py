import json
import re
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from groq import APIStatusError

from src.config import load_config, settings
from src.errors import PipelineError
from src.evidence import select_passages
from src.llm import TokenPacer, token_bound
from src.nodes import planner, writer, verifier


def test_models_default_to_working_planner_model(monkeypatch):
    for name in ("PLANNER_MODEL", "WRITER_MODEL", "VERIFIER_MODEL", "GROQ_MODEL"):
        monkeypatch.delenv(name, raising=False)
    # Legacy MODEL_NAME must not select the unavailable writer model.
    monkeypatch.setenv("MODEL_NAME", "llama3-8b-8192")
    config = load_config()
    assert config.writer_model == config.planner_model == config.verifier_model == "openai/gpt-oss-120b"


def test_role_model_overrides_shared_default(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "shared-model")
    monkeypatch.setenv("WRITER_MODEL", "writer-only")
    monkeypatch.delenv("PLANNER_MODEL", raising=False)
    monkeypatch.delenv("VERIFIER_MODEL", raising=False)
    config = load_config()
    assert config.writer_model == "writer-only"
    assert config.planner_model == config.verifier_model == "shared-model"

def evidence(index=0, content=None):
    return {'title': f'OpenAI model announcement {index}',
            'url': f'https://example.com/news/{index}', 'source_type': 'article',
            'content': content or f'OpenAI announced model {index}. It improves inference speed.',
            'topic': 'OpenAI'}


def test_large_multilingual_sources_are_batched_and_originals_retained(monkeypatch):
    sources = [evidence(index, ('\u0905\u0928\u0941\u0938\u0902\u0927\u093e\u0928. OpenAI inference report. ' * 3000) + f' Model {index}.')
               for index in range(17)]
    prompts = []
    def generate(prompt):
        assert token_bound(prompt) + 128 <= settings.llm_input_budget
        prompts.append(prompt)
        urls = re.findall(r'^URL: (.+)$', prompt, flags=re.M)
        return '## OpenAI\n\n' + '\n\n'.join(f'- [New model]({url}): OpenAI announced a model.' for url in urls)
    monkeypatch.setattr(writer, '_generate_digest', generate)
    state = {'sources': sources, 'interests': ['OpenAI']}
    update = writer.writer_node(state)
    assert len(prompts) > 1
    assert sum(len(batch['sources']) for batch in update['draft_batches']) == 17
    assert all(token_bound(source['content']) > 100000 for source in state['sources'])
    assert sources[0]['url'] in update['draft'] and sources[-1]['url'] in update['draft']
    verification_prompts = []
    def verify(prompt):
        assert token_bound(prompt) + 128 <= settings.llm_input_budget
        verification_prompts.append(prompt)
        return '{"score": 95, "issues": []}'
    monkeypatch.setattr(verifier, '_generate_verification', verify)
    result = verifier.verifier_node({**state, **update})
    assert result['verification_score'] == 95
    assert len(verification_prompts) == 17


def test_passage_selection_can_find_evidence_after_long_introduction():
    content = ('Unrelated weather report.\n\n' * 100) + 'OpenAI released the quantum model with a new inference engine.'
    excerpt = select_passages(content, 'OpenAI quantum inference', limit=400)
    assert 'quantum model' in excerpt
    assert token_bound(excerpt) <= 400


def test_transcript_without_punctuation_keeps_relevant_late_passages():
    content = ('unrelated introduction ' * 500) + 'OpenAI quantum inference demonstration announced'
    excerpt = select_passages(content, 'OpenAI quantum inference demonstration', limit=1600)
    assert 'OpenAI quantum inference' in excerpt
    assert token_bound(excerpt) <= 1600


def test_short_sources_do_not_overload_writer_output(monkeypatch):
    seen = []
    def generate(prompt):
        urls = re.findall(r'^URL: (.+)$', prompt, flags=re.M)
        seen.append(len(urls))
        return '\n\n'.join(f'- [News]({url}): A model was announced.' for url in urls)
    monkeypatch.setattr(writer, '_generate_digest', generate)
    writer.writer_node({'sources': [evidence(index) for index in range(12)]})
    assert sum(seen) == 12
    assert max(seen) <= 3


def test_writer_failure_is_not_returned_as_a_digest(monkeypatch):
    def fail(prompt):
        raise PipelineError('Model unavailable')
    monkeypatch.setattr(writer, '_generate_digest', fail)
    with pytest.raises(PipelineError, match='Model unavailable'):
        writer.writer_node({'sources': [evidence()]})


def test_no_sources_stops_before_llm(monkeypatch):
    generate = MagicMock()
    monkeypatch.setattr(writer, '_generate_digest', generate)
    with pytest.raises(PipelineError, match='No usable news sources'):
        writer.writer_node({'sources': []})
    generate.assert_not_called()


def test_verifier_failure_is_not_scored_as_bad_journalism(monkeypatch):
    def fail(prompt):
        raise PipelineError('Provider failed')
    monkeypatch.setattr(verifier, '_generate_verification', fail)
    with pytest.raises(PipelineError, match='Provider failed'):
        verifier.verifier_node({'draft': '- [News](https://example.com/news/0): OpenAI announced a model.',
                                'sources': [evidence()]})


@pytest.mark.parametrize('response', ['not JSON', '{"score": 500, "issues": []}',
                                     '{"score": NaN, "issues": []}', '{"score": 90}'])
def test_invalid_verification_is_a_pipeline_error(monkeypatch, response):
    monkeypatch.setattr(verifier, '_generate_verification', lambda _: response)
    with pytest.raises(PipelineError, match='invalid JSON'):
        verifier.verifier_node({'draft': '- [News](https://example.com/news/0): OpenAI announced a model.',
                                'sources': [evidence()]})


def test_unknown_citation_cannot_receive_a_passing_score(monkeypatch):
    monkeypatch.setattr(verifier, '_generate_verification', lambda _: '{"score": 100, "issues": []}')
    result = verifier.verifier_node({'draft': '- [News](https://unknown.example/story): Model launched.',
                                    'sources': [evidence()]})
    assert result['verification_score'] == 0
    assert 'unknown' in result['verification_issues'][0]


def test_pacer_respects_sliding_window_and_actual_usage(monkeypatch):
    monkeypatch.setattr(settings, 'groq_tpm_limit', 8000)
    now = [0.0]
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds
    pacer = TokenPacer(clock=lambda: now[0], sleep=sleep)
    first = pacer.reserve(6000)
    pacer.complete(first, 1000)
    second = pacer.reserve(6000)
    assert not waits
    pacer.complete(second, 6000)
    pacer.reserve(2000)
    assert sum(waits) == 61
    assert max(waits) <= 30


def test_llm_wrapper_uses_model_and_limits_and_tracks_usage(monkeypatch):
    from src import llm
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        usage=SimpleNamespace(total_tokens=400),
        choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='Result'))])
    monkeypatch.setattr('groq.Groq', lambda **kwargs: client)
    monkeypatch.setattr(settings, 'groq_api_key', 'test')
    now = [0.0]
    monkeypatch.setattr(llm, 'pacer', TokenPacer(clock=lambda: now[0], sleep=lambda seconds: None))
    assert llm.generate_text('Test prompt', model='openai/gpt-oss-120b', stage='Writer') == 'Result'
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs['model'] == 'openai/gpt-oss-120b'
    assert kwargs['max_completion_tokens'] == settings.llm_output_budget
    assert kwargs['reasoning_effort'] == 'low'
    assert llm.pacer.reservations[0].tokens == 400
    client.close.assert_called_once()


@pytest.mark.parametrize('status,expected', [(401, 'API key'), (404, 'WRITER_MODEL'), (413, 'request size')])
def test_nonretryable_api_errors_stop_once(monkeypatch, status, expected):
    from src import llm
    client = MagicMock()
    client.chat.completions.create.side_effect = APIStatusError(
        'Test error', response=httpx.Response(status, request=httpx.Request('POST', 'https://api.groq.com')), body={})
    monkeypatch.setattr('groq.Groq', lambda **kwargs: client)
    monkeypatch.setattr(settings, 'groq_api_key', 'test')
    monkeypatch.setattr(llm, 'pacer', TokenPacer())
    with pytest.raises(PipelineError, match=expected):
        llm.generate_text('Test', model='test-model', stage='Writer')
    assert client.chat.completions.create.call_count == 1


def test_oversized_input_never_reaches_provider(monkeypatch):
    from src import llm
    client_factory = MagicMock()
    monkeypatch.setattr('groq.Groq', client_factory)
    monkeypatch.setattr(settings, 'groq_api_key', 'test')
    with pytest.raises(PipelineError, match='input exceeds'):
        llm.generate_text('x' * 50000, model='test', stage='Writer')
    client_factory.assert_not_called()


def test_truncated_output_is_not_a_completed_digest(monkeypatch):
    from src import llm
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        usage=SimpleNamespace(total_tokens=400),
        choices=[SimpleNamespace(finish_reason='length', message=SimpleNamespace(content='Partial'))])
    monkeypatch.setattr('groq.Groq', lambda **kwargs: client)
    monkeypatch.setattr(settings, 'groq_api_key', 'test')
    monkeypatch.setattr(llm, 'pacer', TokenPacer())
    with pytest.raises(PipelineError, match='truncated'):
        llm.generate_text('Test', model='test', stage='Writer')


@pytest.mark.parametrize('url', [
    'https://in.linkedin.com/in/someone', 'https://www.instagram.com/p/abc',
    'https://www.reddit.com/r/India/new', 'https://x.com/person/status/123',
    'https://www.youtube.com/watch?v=123', 'https://tavily.com/knowledge/company/123',
    'https://finance.yahoo.com/quote/NVDA', 'https://example.com/',
    'https://example.com/category', 'https://example.com/news/feed',
])
def test_profile_and_listing_pages_are_not_articles(url):
    from src.nodes.researcher import _is_non_article_url
    assert _is_non_article_url(url)


def test_regular_yahoo_article_is_retained():
    from src.nodes.researcher import _is_non_article_url
    assert not _is_non_article_url('https://finance.yahoo.com/news/nvidia-announces-new-gpu-123.html')


def test_403_article_is_not_requested_three_times(monkeypatch):
    import requests
    from src.tools.fetcher import ArticleFetcher
    response = MagicMock()
    response.status_code = 403
    response.raise_for_status.side_effect = requests.HTTPError('Blocked', response=response)
    get = MagicMock(return_value=response)
    monkeypatch.setattr('src.tools.fetcher.requests.get', get)
    assert ArticleFetcher().fetch('https://example.com/blocked') is None
    get.assert_called_once()


@pytest.mark.parametrize('html', [
    '<html><meta name="description" content="A news story"></html>',
    '<article><p>This is too short to be an article.</p></article>',
    '<article><p>Verify you are human. ' + ('Check your browser. ' * 30) + '</p></article>',
])
def test_empty_short_or_challenge_pages_are_rejected(monkeypatch, html):
    from src.tools.fetcher import ArticleFetcher
    response = MagicMock()
    response.text = html
    monkeypatch.setattr('src.tools.fetcher.requests.get', lambda *args, **kwargs: response)
    assert ArticleFetcher().fetch('https://example.com/article') is None


def test_tracking_urls_and_repeated_content_are_deduplicated(monkeypatch):
    from src.nodes import researcher
    long_content = 'OpenAI announced a significant development in inference speed. ' * 10
    a = evidence(1, long_content)
    b = {**a, 'url': a['url'] + '?utm_source=test#fragment'}
    c = {**a, 'url': 'https://another.example/syndicated-story'}
    d = evidence(2, 'OpenAI released another model. ' * 20)
    monkeypatch.setattr(researcher, '_fetch_articles', lambda *args: [a, b, c, d])
    monkeypatch.setattr(researcher, '_fetch_videos', lambda *args: [])
    state = researcher.researcher_node({'interests': ['OpenAI']})
    assert len(state['sources']) == 2


def test_source_cap_keeps_room_for_videos_and_query_work_is_bounded(monkeypatch):
    from src.nodes import researcher
    monkeypatch.setattr(settings, 'research_max_sources', 2)
    monkeypatch.setattr(settings, 'research_max_queries', 2)
    article_fetch = MagicMock(return_value=[evidence(i) for i in range(8)])
    video = {**evidence(9), 'url': 'https://www.youtube.com/watch?v=123', 'source_type': 'youtube'}
    video_fetch = MagicMock(return_value=[video])
    monkeypatch.setattr(researcher, '_fetch_articles', article_fetch)
    monkeypatch.setattr(researcher, '_fetch_videos', video_fetch)
    state = researcher.researcher_node({'interests': ['OpenAI'],
                                       'web_queries': ['one', 'two', 'three'],
                                       'youtube_queries': ['one', 'two', 'three']})
    assert len(state['sources']) == 2
    assert {source['source_type'] for source in state['sources']} == {'article', 'youtube'}
    assert len(article_fetch.call_args.args[0]) == len(video_fetch.call_args.args[0]) == 2


def test_youtube_reports_search_and_transcript_failure_types(monkeypatch, caplog):
    from src.tools.youtube import YouTubeFetcher
    import requests
    good_response = MagicMock()
    good_response.json.return_value = {'items': [{'id': {'videoId': 'abc'}, 'snippet': {
        'title': 'News', 'publishedAt': datetime.now(timezone.utc).isoformat()}}]}
    bad_response = MagicMock()
    bad_response.status_code = 403
    bad_response.json.return_value = {'error': {'errors': [{'reason': 'quotaExceeded'}]}}
    bad_response.raise_for_status.side_effect = requests.HTTPError('key=DO_NOT_LOG_THIS', response=bad_response)
    monkeypatch.setattr('src.tools.youtube.requests.get', MagicMock(side_effect=[good_response, bad_response]))
    transcripts = MagicMock()
    transcripts.fetch.side_effect = RuntimeError('DO_NOT_LOG_THIS')
    end = datetime.now(timezone.utc) + timedelta(seconds=1)
    with caplog.at_level('INFO'):
        assert YouTubeFetcher(api_key='DO_NOT_LOG_THIS', transcript_client=transcripts).fetch(
            'news', 'news', end-timedelta(hours=24), end) == []
    assert 'count=1' in caplog.text
    assert 'reason=RuntimeError' in caplog.text and 'reason=quotaExceeded' in caplog.text
    assert 'transcript_failures=1' in caplog.text
    assert 'DO_NOT_LOG_THIS' not in caplog.text


def test_pipeline_error_reaches_rest_and_stream_without_done(monkeypatch):
    from src.api.main import app
    from fastapi.testclient import TestClient
    graph = MagicMock()
    graph.invoke.side_effect = PipelineError('Writer model unavailable. Check WRITER_MODEL.')
    def stream(*args, **kwargs):
        yield {'planner_node': {'plan': '{}'}}
        raise PipelineError('Writer model unavailable. Check WRITER_MODEL.')
    graph.stream.side_effect = stream
    monkeypatch.setattr('src.api.router.graph_app', graph)
    client = TestClient(app)
    response = client.post('/api/research', json={'query': 'OpenAI'})
    assert response.status_code == 502
    assert 'WRITER_MODEL' in response.json()['detail']
    events = client.get('/api/research/stream', params={'q': 'OpenAI'}).text
    assert '"event": "error"' in events and 'WRITER_MODEL' in events
    assert '"event": "done"' not in events


def test_real_workflow_does_not_verify_or_save_after_writer_failure(tmp_path, monkeypatch):
    from src.graph.workflow import app
    from src.nodes import researcher
    monkeypatch.setattr(settings, 'database_path', str(tmp_path / 'failed.sqlite3'))
    monkeypatch.setattr(planner, '_generate_search_plan', lambda _: json.dumps({
        'web_queries': ['OpenAI'], 'youtube_queries': ['OpenAI briefing']}))
    monkeypatch.setattr(researcher, '_fetch_articles', lambda *args: [evidence()])
    monkeypatch.setattr(researcher, '_fetch_videos', lambda *args: [])
    def fail(prompt):
        raise PipelineError('Writer model unavailable')
    monkeypatch.setattr(writer, '_generate_digest', fail)
    verify = MagicMock()
    monkeypatch.setattr(verifier, '_generate_verification', verify)
    with pytest.raises(PipelineError, match='Writer model unavailable'):
        app.invoke({'interests': ['OpenAI'], 'retry_count': 0})
    verify.assert_not_called()
    assert not (tmp_path / 'failed.sqlite3').exists()


def test_real_workflow_stores_full_sources_after_bounded_verification(tmp_path, monkeypatch):
    import sqlite3
    from src.graph.workflow import app
    from src.nodes import researcher
    monkeypatch.setattr(settings, 'database_path', str(tmp_path / 'success.sqlite3'))
    monkeypatch.setattr(planner, '_generate_search_plan', lambda _: json.dumps({
        'web_queries': ['OpenAI'], 'youtube_queries': ['OpenAI briefing']}))
    original = evidence(content='OpenAI announced a model with better inference.\n\n' * 1000)
    monkeypatch.setattr(researcher, '_fetch_articles', lambda *args: [original])
    monkeypatch.setattr(researcher, '_fetch_videos', lambda *args: [])
    monkeypatch.setattr(writer, '_generate_digest', lambda _: '## OpenAI\n\n- [News](https://example.com/news/0): OpenAI announced a model.')
    monkeypatch.setattr(verifier, '_generate_verification', lambda _: '{"score": 95, "issues": []}')
    result = app.invoke({'interests': ['OpenAI'], 'retry_count': 0})
    with sqlite3.connect(settings.database_path) as connection:
        rows = connection.execute('SELECT sources_json, digest_markdown FROM news_feeds').fetchall()
    assert len(rows) == 1
    assert json.loads(rows[0][0])[0]['content'] == original['content'].strip()
    assert rows[0][1] == result['final_digest']
