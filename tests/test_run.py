import json

import mock
import httpretty
from requests.exceptions import ConnectionError
import pytest

from httsleep.main import HttSleep, HttSleepError

URL = 'http://example.com'


@httpretty.activate
def test_run_success():
    """Should return response when a success criteria has been reached"""
    httpretty.register_uri(httpretty.GET, URL, body='<html></html>', status=200)
    with mock.patch('httsleep.main.sleep') as mock_sleep:
        httsleep = HttSleep(URL, {'status_code': 200})
        resp = httsleep.run()
        assert resp.status_code == 200
        assert not mock_sleep.called


@httpretty.activate
def test_run_error():
    """Should raise an HttSleepError when a failure criteria has been reached"""
    httpretty.register_uri(httpretty.GET, URL, body='<html></html>', status=400)
    httsleep = HttSleep(URL, {'status_code': 200}, error={'status_code': 400})
    with pytest.raises(HttSleepError):
        httsleep.run()


@httpretty.activate
def test_run_success_error():
    """Make sure failure criteria takes precedence over success criteria (if httsleep is being used incorrectly)"""
    httpretty.register_uri(httpretty.GET, URL, body='', status=200)
    httsleep = HttSleep(URL, {'status_code': 200}, error={'text': ''})
    with pytest.raises(HttSleepError):
        httsleep.run()


@httpretty.activate
def test_run_retries():
    """Should retry until a success condition is reached"""
    responses = [httpretty.Response(body="Internal Server Error", status=500),
                 httpretty.Response(body="Internal Server Error", status=500),
                 httpretty.Response(body="<html></html>", status=200)]
    httpretty.register_uri(httpretty.GET, URL, responses=responses)
    with mock.patch('httsleep.main.sleep') as mock_sleep:
        resp = HttSleep(URL, {'status_code': 200}).run()
        assert mock_sleep.called
        assert mock_sleep.call_count == 2
    assert resp.status_code == 200
    assert resp.text == '<html></html>'


@httpretty.activate
def test_run_max_retries():
    """Should raise an exception when max_retries is reached"""
    responses = [httpretty.Response(body="Internal Server Error", status=500),
                 httpretty.Response(body="Internal Server Error", status=500),
                 httpretty.Response(body="Internal Server Error", status=500)]
    httpretty.register_uri(httpretty.GET, URL, responses=responses)
    with mock.patch('httsleep.main.sleep'):
        httsleep = HttSleep(URL, {'status_code': 200}, max_retries=2)
        with pytest.raises(StopIteration):
            httsleep.run()


@httpretty.activate
def test_ignore_exceptions():
    responses = [httpretty.Response(body=ConnectionError),
                 httpretty.Response(body="{}", status=200)]
    httpretty.register_uri(httpretty.GET, URL, responses=responses)
    with mock.patch('httsleep.main.sleep'):
        httsleep = HttSleep(URL, {'json': {}}, ignore_exceptions=[ConnectionError])
        resp = httsleep.run()
    assert resp.status_code == 200
    assert resp.text == "{}"


@httpretty.activate
def test_json_condition():
    expected = {'my_key': 'my_value'}
    responses = [httpretty.Response(body=json.dumps({'error': 'not found'}), status=404),
                 httpretty.Response(body=json.dumps(expected), status=200)]
    httpretty.register_uri(httpretty.GET, URL, responses=responses)
    with mock.patch('httsleep.main.sleep'):
        httsleep = HttSleep(URL, {'json': expected})
        resp = httsleep.run()
    assert resp.status_code == 200
    assert resp.json() == expected


@httpretty.activate
def test_text_condition():
    expected = 'you got it!'
    responses = [httpretty.Response(body='not found', status=404),
                 httpretty.Response(body=expected, status=200)]
    httpretty.register_uri(httpretty.GET, URL, responses=responses)
    with mock.patch('httsleep.main.sleep'):
        httsleep = HttSleep(URL, {'text': expected})
        resp = httsleep.run()
    assert resp.status_code == 200
    assert resp.text == expected


# @pytest.skip
# @httpretty.activate
# def test_jsonpath_condition():
#     raise NotImplementedError()


@httpretty.activate
def test_multiple_success_conditions():
    responses = [httpretty.Response(body='first response', status=200),
                 httpretty.Response(body='second response', status=200),
                 httpretty.Response(body='third response', status=200)]
    httpretty.register_uri(httpretty.GET, URL, responses=responses)
    conditions = [{'text': 'third response', 'status_code': 200},
                  {'text': 'second response', 'status_code': 200}]
    with mock.patch('httsleep.main.sleep'):
        httsleep = HttSleep(URL, conditions)
        resp = httsleep.run()
    assert resp.status_code == 200
    assert resp.text == 'second response'


@httpretty.activate
def test_multiple_error_conditions():
    error_msg = {'status': 'ERROR'}
    responses = [httpretty.Response(body=json.dumps(error_msg), status=500),
                 httpretty.Response(body='Internal Server Error', status=500),
                 httpretty.Response(body='success', status=200)]
    httpretty.register_uri(httpretty.GET, URL, responses=responses)
    conditions = [{'text': 'Internal Server Error', 'status_code': 500},
                  {'json': error_msg, 'status_code': 500}]
    with mock.patch('httsleep.main.sleep'):
        httsleep = HttSleep(URL, {'status_code': 200}, error=conditions)
        try:
            httsleep.run()
        except HttSleepError as e:
            assert e.response.status_code == 500
            assert e.response.json() == error_msg
            assert e.error_condition == {'json': error_msg, 'status_code': 500}
        else:
            pytest.fail("No exception raised!")