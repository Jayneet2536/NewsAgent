from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import json
import sqlite3

import pytest

from src.models import NewsSource
from src.nodes import planner, researcher
from src.tools.time_window import parse_timestamp
from src.tools.youtube import YouTubeFetcher
from src.database import persist_feed_node
from src.config import settings

END = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
START = END - timedelta(hours=24)


def source(url='https://example.com/news', published_at=None, **kwargs):
    return NewsSource(title='OpenAI news', url=url, source_type='article',
                      content='OpenAI announced a new model.', topic='OpenAI',
                      published_at=published_at, **kwargs)


def test_planner_validates_structured_plan_and_falls_back(monkeypatch):
    monkeypatch.setattr(planner, '_generate_search_plan', lambda _: '{"web_queries":["OpenAI news"],"youtube_queries":["OpenAI demonstration"]}')
    result = planner.planner_node({'interests': ['OpenAI']})
    assert json.loads(result['plan'])['youtube_queries'] == ['OpenAI demonstration']
    monkeypatch.setattr(planner, '_generate_search_plan', lambda _: '{"web_queries": [""]}')
    result = planner.planner_node({'interests': ['OpenAI']})
    assert result['web_queries'] and result['youtube_queries']
    assert '24 hours' not in result['plan']


@pytest.mark.parametrize('timestamp', ['2026-11-22', 'garbage', None, '2026-11-22T10:00:00'])
def test_uncertain_timestamps_are_unknown(timestamp):
    assert parse_timestamp(timestamp) is None


def test_rfc_timestamp_is_utc():
    assert parse_timestamp('Sun, 22 Nov 2026 12:00:00 GMT') == END


def test_research_filters_time_duplicates_and_irrelevant_content(monkeypatch):
    now = datetime.now(timezone.utc)
    candidates = [source(published_at=now-timedelta(hours=1)), source(),
                  source('https://example.com/old', now-timedelta(hours=25)),
                  source('https://example.com/future', now+timedelta(hours=1)),
                  source('https://example.com/unknown')]
    irrelevant = source('https://example.com/sport').model_copy(update={'title': 'Cricket', 'content': 'A cricket match was played.'})
    monkeypatch.setattr(researcher, '_fetch_articles', lambda *args: candidates + [irrelevant])
    monkeypatch.setattr(researcher, '_fetch_videos', lambda *args: [])
    result = researcher.researcher_node({'interests': ['OpenAI']})
    assert len(result['sources']) == 2
    assert result['sources'] == result['articles']
    assert datetime.fromisoformat(result['window_end']) - datetime.fromisoformat(result['window_start']) == timedelta(hours=24)


def test_provider_failure_retains_other_sources(monkeypatch):
    def fail(*args):
        raise RuntimeError('provider down')
    monkeypatch.setattr(researcher, '_fetch_articles', fail)
    monkeypatch.setattr(researcher, '_fetch_videos', lambda *args: [source()])
    assert len(researcher.researcher_node({'interests': ['OpenAI']})['sources']) == 1


def test_youtube_uses_window_durations_and_skips_bad_transcripts(monkeypatch):
    items = [{'id': {'videoId': video_id}, 'snippet': {
        'title': 'OpenAI briefing', 'publishedAt': published,
        'channelTitle': 'OpenAI', 'description': 'Model demonstration',
        'thumbnails': {'high': {'url': 'https://example.com/image.jpg'}}}}
        for video_id, published in [('good', END.isoformat()), ('blocked', END.isoformat()),
                                    ('old', (START-timedelta(seconds=1)).isoformat()),
                                    ('empty', END.isoformat())]]
    response = MagicMock()
    response.json.return_value = {'items': items}
    get = MagicMock(return_value=response)
    monkeypatch.setattr('src.tools.youtube.requests.get', get)
    transcripts = MagicMock()
    def fetch(video_id):
        if video_id == 'blocked':
            raise RuntimeError('blocked')
        return [SimpleNamespace(text='OpenAI announced a model.')] if video_id == 'good' else []
    transcripts.fetch.side_effect = fetch
    sources = YouTubeFetcher(api_key='test-key', transcript_client=transcripts).fetch('OpenAI', 'AI', START, END)
    assert len(sources) == 1
    assert sources[0].source_type == 'youtube'
    assert sources[0].content == 'OpenAI announced a model.'
    assert sources[0].publisher == 'OpenAI'
    assert {call.kwargs['params']['videoDuration'] for call in get.call_args_list} == {'medium', 'long'}
    for call in get.call_args_list:
        params = call.kwargs['params']
        assert params['publishedAfter'] == START.isoformat().replace('+00:00', 'Z')
        assert params['publishedBefore'] == END.isoformat().replace('+00:00', 'Z')
        assert params['type'] == 'video' and params['order'] == 'date'
    assert 'old' not in [call.args[0] for call in transcripts.fetch.call_args_list]


def test_tavily_preserves_dates_and_filters_exact_window(monkeypatch):
    from src.tools.search import TavilySearch
    client = MagicMock()
    client.search.return_value = {'results': [
        {'url': 'https://example.com/current', 'published_date': END.isoformat()},
        {'url': 'https://example.com/old', 'published_date': (START-timedelta(seconds=1)).isoformat()},
        {'url': 'https://example.com/unknown'}]}
    monkeypatch.setattr('src.tools.search.TavilyClient', lambda **kwargs: client)
    results = TavilySearch('test').search('news', window_start=START, window_end=END)
    assert len(results) == 2 and results[0]['published_at'] == END
    assert client.search.call_args.kwargs['days'] == 1


def test_persistence_stores_final_digest_evidence_and_time(tmp_path, monkeypatch):
    path = tmp_path / 'feeds.sqlite3'
    monkeypatch.setattr(settings, 'database_path', str(path))
    evidence = [source().model_dump(mode='json')]
    result = persist_feed_node({'draft': 'Final feed', 'sources': evidence,
                               'verification_score': 90, 'plan': '{}'})
    with sqlite3.connect(path) as connection:
        row = connection.execute('SELECT stored_at, digest_markdown, sources_json FROM news_feeds WHERE id=?', (result['feed_id'],)).fetchone()
    assert row[0] == result['stored_at']
    assert datetime.fromisoformat(row[0]).utcoffset() == timedelta(0)
    assert row[1] == result['final_digest'] == 'Final feed'
    assert json.loads(row[2]) == evidence


def test_graph_persists_only_after_final_rewrite(tmp_path, monkeypatch):
    from langgraph.graph import StateGraph, END as GRAPH_END
    from src.graph.state import AgentState
    from src.graph.workflow import should_continue
    monkeypatch.setattr(settings, 'database_path', str(tmp_path / 'graph.sqlite3'))
    monkeypatch.setattr(settings, 'max_retries', 2)
    workflow = StateGraph(AgentState)
    workflow.add_node('writer', lambda s: {'draft': f"Draft {s.get('retry_count', 0)}"})
    workflow.add_node('verifier', lambda s: {'retry_count': s.get('retry_count', 0)+1, 'verification_score': 0})
    workflow.add_node('persist', persist_feed_node)
    workflow.set_entry_point('writer')
    workflow.add_edge('writer', 'verifier')
    workflow.add_conditional_edges('verifier', should_continue, {'rewrite': 'writer', 'end': 'persist'})
    workflow.add_edge('persist', GRAPH_END)
    result = workflow.compile().invoke({'interests': ['AI'], 'retry_count': 0})
    assert result['final_digest'] == 'Draft 1'
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute('SELECT count(*) FROM news_feeds').fetchone()[0] == 1


def test_rest_and_stream_include_video_metadata_and_storage_time(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.main import app
    evidence = source(url='https://www.youtube.com/watch?v=example',
                      published_at=END).model_dump(mode='json')
    evidence['source_type'] = 'youtube'
    state = {'interests': ['AI'], 'plan': '{}', 'sources': [evidence],
             'final_digest': 'Saved digest', 'verification_score': 90,
             'feed_id': 42, 'stored_at': END.isoformat()}
    graph = MagicMock()
    graph.invoke.return_value = state
    graph.stream.return_value = iter([{'persist_feed_node': state}])
    monkeypatch.setattr('src.api.router.graph_app', graph)
    client = TestClient(app)
    response = client.post('/api/research', json={'query': 'AI'})
    assert response.status_code == 200
    body = response.json()
    assert body['feed_id'] == 42 and body['stored_at'].endswith('Z')
    assert body['sections'][0]['articles'][0]['source_type'] == 'youtube'
    assert 'content' not in body['sections'][0]['articles'][0]
    stream = client.get('/api/research/stream', params={'q': 'AI'})
    events = [json.loads(line.removeprefix('data: ')) for line in stream.text.splitlines() if line.startswith('data: ')]
    done = next(event for event in events if event['event'] == 'done')
    assert done['data']['feed_id'] == 42
    assert done['data']['stored_at'].endswith('Z')


def test_writer_and_verifier_receive_original_transcript():
    from src.nodes.writer import _format_articles
    from src.nodes.verifier import _format_sources
    evidence = source().model_dump(mode='json')
    evidence['source_type'] = 'youtube'
    evidence['content'] = 'A long introduction. ' * 100 + 'The model was released.'
    for formatter in (_format_articles, _format_sources):
        context = formatter([evidence])
        assert 'The model was released.' in context
        assert evidence['url'] in context
        assert 'youtube' in context
