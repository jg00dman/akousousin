import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from akousousin_app import settings
from akousousin_app.speech_dispatcher import Module, chunks, escaped, install, uninstall, speech_parts, accessible_text
from test_backend import audio


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'settings.json'
        settings.save(self.path, dict(settings.DEFAULTS, voice='english', voices={
            'english': {'name': 'English', 'language': 'en_US', 'sample_rate': 22050}}))

    def test_handshake_settings_voice_list_and_quit(self):
        source = io.BytesIO(b'INIT\nAUDIO\naudio_output_method=server\n.\nSET\nrate=20\n.\nLIST VOICES\nQUIT\n')
        output = io.BytesIO()
        Module(self.path, source, output).run()
        response = output.getvalue()
        self.assertIn(b'299 OK LOADED SUCCESSFULLY', response)
        self.assertIn(b'200-english\ten-US\tnone\n', response)
        self.assertIn(b'210 OK QUIT', response)
        self.assertNotIn(b'303 ', response)

    def test_multiline_dot_unstuffing_and_size_limit(self):
        module = Module(self.path, io.BytesIO(b'one\n..two\n.\n'), io.BytesIO())
        self.assertEqual(module.block(), 'one\n.two')
        module.source = io.BytesIO(b'x' * 65537 + b'\n.\n')
        with self.assertRaises(ValueError):
            module.block()

    def test_chunking_preserves_text_and_escape_roundtrip(self):
        text = 'A sentence with Unicode café. ' * 100
        pieces = list(chunks(text))
        self.assertEqual(''.join(pieces), text)
        self.assertTrue(all(0 < len(piece) <= 241 for piece in pieces))
        self.assertEqual(escaped(b'\x00\n}\x80'), b'\x00}*}]\x80')

    def test_bad_settings_and_unsupported_audio_are_rejected(self):
        output = io.BytesIO()
        Module(self.path, io.BytesIO(b'INIT\nSET\nrate=101\n.\nAUDIO\naudio_output_method=alsa\n.\nQUIT\n'), output).run()
        self.assertEqual(output.getvalue().count(b'303 ERROR'), 2)

    @patch('akousousin_app.speech_dispatcher.runtime.call')
    @patch('akousousin_app.speech_dispatcher.fetch')
    def test_speech_returns_pcm_to_dispatcher_and_finishes(self, open_request, wake):
        open_request.return_value = audio(22050)
        output = io.BytesIO()
        module = Module(self.path, output=output)
        module.audio_server = True
        module.speak('Hello')
        module.task.join(2)
        self.assertFalse(module.task.is_alive())
        response = output.getvalue()
        self.assertIn(b'701 BEGIN\n', response)
        self.assertIn(b'705-AUDIO\0', response)
        self.assertTrue(response.endswith(b'702 END\n'))
        payload = open_request.call_args[0][1]
        self.assertEqual(json.loads(payload)['voice'], 'english')

    @patch('akousousin_app.speech_dispatcher.runtime.call')
    @patch('akousousin_app.speech_dispatcher.fetch')
    def test_stop_is_immediate_and_late_response_emits_no_audio(self, open_request, wake):
        entered, release = threading.Event(), threading.Event()
        def blocked(*args, **kwargs):
            entered.set()
            release.wait(2)
            return audio(22050)
        open_request.side_effect = blocked
        module = Module(self.path, output=io.BytesIO())
        module.audio_server = True
        module.speak('Hello')
        self.assertTrue(entered.wait(1))
        module.stop()
        self.assertIn(b'703 STOP\n', module.output.getvalue())
        release.set()
        module.task.join(2)
        self.assertNotIn(b'705-AUDIO', module.output.getvalue())
        self.assertNotIn(b'702 END', module.output.getvalue())

    def test_user_install_is_idempotent_and_preserves_existing_config(self):
        with patch.dict('os.environ', {'XDG_CONFIG_HOME': str(self.root / 'config'),
                                      'XDG_DATA_HOME': str(self.root / 'data')}):
            directory = self.root / 'config/speech-dispatcher'
            directory.mkdir(parents=True)
            path = directory / 'speechd.conf'
            path.write_text('DefaultModule "espeak-ng"\n')
            install(self.path)
            install(self.path)
            text = path.read_text()
            self.assertTrue(text.startswith('DefaultModule "espeak-ng"'))
            self.assertEqual(text.count('AddModule "akousousin"'), 1)
            launcher = self.root / 'data/Akousousin/speech-dispatcher-module'
            self.assertTrue(launcher.stat().st_mode & 0o100)
            self.assertIn('--speech-dispatcher', launcher.read_text())


    def test_orca_ssml_entities_and_marks_are_not_spoken(self):
        text = '<speak><mark name="0:5"/>Hello &amp; café.<mark name="__spd_0"/><mark name="14:19"/> Next.</speak>'
        parts = list(speech_parts(text))
        self.assertEqual(''.join(part for _, part in parts), 'Hello & café. Next.')
        self.assertEqual(parts[0][0], '0:5')
        self.assertIn('__spd_0', [mark for mark, _ in parts])
        with self.assertRaises(ValueError):
            list(speech_parts('<speak><mark name="bad&#10;700 forged"/>Text</speak>'))

    def test_accessibility_symbols_spelling_and_capitals(self):
        self.assertEqual(accessible_text(' ', {}, True), 'space')
        self.assertEqual(accessible_text('A!', {'cap_let_recogn': 'spell'}, True), 'capital A exclamation mark')
        self.assertIn('comma', accessible_text('a,b', {'punctuation_mode': 'all'}))
        self.assertEqual(accessible_text('cat', {'spelling_mode': 'on'}), 'c a t')

    @patch('akousousin_app.speech_dispatcher.runtime.call')
    @patch('akousousin_app.speech_dispatcher.fetch')
    def test_orca_marks_precede_associated_pcm(self, fetch, wake):
        fetch.return_value = audio(22050)
        module = Module(self.path, output=io.BytesIO())
        module.audio_server = True
        module.speak('<speak><mark name="0:5"/>Hello &amp; café</speak>')
        module.task.join(2)
        result = module.output.getvalue()
        self.assertLess(result.index(b'700-0:5'), result.index(b'705-AUDIO'))
        self.assertEqual(json.loads(fetch.call_args.args[1])['text'], 'Hello & café')

    def test_uninstall_preserves_other_modules_and_defaults(self):
        with patch.dict('os.environ', {'XDG_CONFIG_HOME': str(self.root / 'config'),
                                      'XDG_DATA_HOME': str(self.root / 'data')}):
            path = install(self.path)
            path.write_text(path.read_text() + 'DefaultModule "espeak-ng"\nAddModule "other" "/other" ""\n')
            uninstall(self.path)
            uninstall(self.path)
            self.assertNotIn('AddModule "akousousin"', path.read_text())
            self.assertIn('DefaultModule "espeak-ng"', path.read_text())
            self.assertIn('AddModule "other"', path.read_text())


    @patch('akousousin_app.speech_dispatcher.runtime.call')
    @patch('akousousin_app.speech_dispatcher.fetch')
    def test_language_tags_are_case_insensitive_with_regional_fallback(self, fetch, wake):
        fetch.return_value = audio(22050)
        config = settings.load(self.path)
        config['voices']['german'] = {'name': 'German', 'language': 'de_DE', 'sample_rate': 22050}
        config['language_voices']['de_DE'] = 'german'
        settings.save(self.path, config)
        for language in ('DE-de', 'de-AT', 'de'):
            module = Module(self.path, output=io.BytesIO())
            module.audio_server = True
            module.options['language'] = language
            module.speak('Hallo')
            module.task.join(2)
            self.assertEqual(json.loads(fetch.call_args.args[1])['voice'], 'german')


    def test_dispatcher_012_most_punctuation_setting_used_by_orca(self):
        output = io.BytesIO()
        module = Module(self.path, io.BytesIO(b'INIT\nSET\npunctuation_mode=most\n.\nQUIT\n'), output)
        module.run()
        self.assertNotIn(b'303 ERROR', output.getvalue())
        self.assertEqual(module.options['punctuation_mode'], 'most')
        text = accessible_text('a@b.', {'punctuation_mode': 'most'})
        self.assertIn('at', text)
        self.assertTrue(text.endswith('.'))
