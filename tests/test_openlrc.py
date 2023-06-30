#  Copyright (C) 2023. Hao Zheng
#  All rights reserved.

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from openlrc.openlrc import LRCer
from openlrc.transcribe import TranscriptionInfo
from openlrc.utils import extend_filename


@patch('openlrc.transcribe.Transcriber.transcribe',
       MagicMock(return_value=[{'sentences': [
           {'text': 'test sentence1', 'start': 0.0, 'end': 3.0},
           {'text': 'test sentence2', 'start': 3.0, 'end': 6.0}
       ]}, TranscriptionInfo('en', 6.0)]))
class TestLRCer(unittest.TestCase):
    def setUp(self) -> None:
        self.audio_path = Path('data/test_audio.wav')
        self.video_path = Path('data/test_video.mp4')

    def tearDown(self) -> None:
        def clear_paths(input_path):
            transcribed = extend_filename(input_path, '_transcribed').with_suffix('.json')
            optimized = extend_filename(transcribed, '_optimized')
            translated = extend_filename(optimized, '_translated')
            compare_path = extend_filename(input_path, '_compare').with_suffix('.json')

            json_path = input_path.with_suffix('.json')
            lrc_path = input_path.with_suffix('.lrc')
            srt_path = input_path.with_suffix('.srt')

            [p.unlink(missing_ok=True) for p in
             [transcribed, optimized, translated, compare_path, json_path, lrc_path, srt_path]]

        clear_paths(self.audio_path)
        clear_paths(self.video_path)

        self.video_path.with_suffix('.wav').unlink(missing_ok=True)

    @patch('openlrc.translate.GPTTranslator.translate',
           MagicMock(return_value=['test translation1', 'test translation2']))
    def test_single_audio_transcription_translation(self):
        lrcer = LRCer()
        lrcer.run(self.audio_path)

    @patch('openlrc.translate.GPTTranslator.translate',
           MagicMock(return_value=['test translation1', 'test translation2']))
    def test_multiple_audio_transcription_translation(self):
        lrcer = LRCer()
        lrcer.run([self.audio_path, self.video_path])

    #  Tests that an error is raised when an audio file is not found
    def test_audio_file_not_found(self):
        lrcer = LRCer()
        with self.assertRaises(FileNotFoundError):
            lrcer.run('data/invalid.mp3')

    @patch('openlrc.translate.GPTTranslator.translate', MagicMock(side_effect=Exception('test exception')))
    def test_translation_error(self):
        lrcer = LRCer()
        with self.assertRaises(Exception):
            lrcer.run(self.audio_path)

    #  Tests that a video file can be transcribed and translated
    def test_video_file_transcription_translation(self):
        lrcer = LRCer()
        lrcer.run('data/test_video.mp4')
