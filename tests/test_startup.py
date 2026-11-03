from unittest.mock import MagicMock

import pytest
from signaldesk.config import ModelConfig
from signaldesk.startup import start_local_model


@pytest.fixture
def launch_env(monkeypatch, tmp_path):
    from signaldesk import startup
    launcher = tmp_path / "folder with spaces" / "start-colibri.cmd"
    launcher.parent.mkdir()
    launcher.write_text('@echo off')
    connect, popen = MagicMock(side_effect=ConnectionRefusedError), MagicMock()
    monkeypatch.setattr(startup.socket, 'create_connection', connect)
    monkeypatch.setattr(startup.subprocess, 'Popen', popen)
    monkeypatch.setattr(startup.subprocess, 'CREATE_NEW_CONSOLE', 16, raising=False)
    monkeypatch.setattr(startup.sys, 'platform', 'win32')
    return launcher, connect, popen


def test_launches_existing_4b_script(launch_env):
    launcher, _, popen = launch_env
    assert 'start requested' in start_local_model(ModelConfig(), launcher)
    assert popen.call_args.args[0][-1] == f"& '{launcher}' '4b'"
    assert popen.call_args.kwargs['cwd'] == str(launcher.parent)


def test_existing_listener_never_restarted(launch_env):
    launcher, connect, popen = launch_env
    connect.side_effect = None
    assert 'untouched' in start_local_model(ModelConfig(), launcher)
    popen.assert_not_called()


@pytest.mark.parametrize('config', [ModelConfig(model_id='other'), ModelConfig(base_url='http://example.com:8000/v1')])
def test_custom_model_never_replaced(launch_env, config):
    launcher, connect, popen = launch_env
    assert 'custom model' in start_local_model(config, launcher)
    connect.assert_not_called()
    popen.assert_not_called()


def test_missing_launcher_does_not_prevent_app_start(launch_env):
    launcher, _, popen = launch_env
    launcher.unlink()
    assert 'not found' in start_local_model(ModelConfig(), launcher)
    popen.assert_not_called()


def test_launch_failure_is_explained(launch_env):
    launcher, _, popen = launch_env
    popen.side_effect = OSError('PowerShell unavailable')
    assert 'will still open' in start_local_model(ModelConfig(), launcher)


def test_uncertain_port_check_does_not_launch(launch_env):
    launcher, connect, popen = launch_env
    connect.side_effect = TimeoutError()
    assert 'could not safely check' in start_local_model(ModelConfig(), launcher)
    popen.assert_not_called()
