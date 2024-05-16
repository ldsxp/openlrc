#  Copyright (C) 2024. Hao Zheng
#  All rights reserved.

import re

from langcodes import Language
from lingua import LanguageDetectorBuilder

from openlrc.logger import logger

original_prefix = 'Original>'
translation_prefix = 'Translation>'

# instruction prompt modified from https://github.com/machinewrapped/gpt-subtrans
base_instruction = f'''Ignore all previous instructions.
You are a translator tasked with revising and translating subtitles into a target language. Your goal is to ensure accurate, concise, and natural-sounding translations for each line of dialogue. The input consists of transcribed audio, which may contain transcription errors. Your task is to first correct any errors you find in the sentences based on their context, and then translate them to the target language according to the revised sentences.
The user will provide a chunk of lines, you should respond with an accurate, concise, and natural-sounding translation for the dialogue, with appropriate punctuation.
The user may provide additional context, such as background, description or title of the source material, a summary of the current scene, or a list of character names. Use this information to improve the quality of your translation.
Your response will be processed by an automated system, so it is imperative that you adhere to the required output format.
The source subtitles were AI-generated with a speech-to-text tool so they are likely to contain errors. Where the input seems likely to be incorrect, use ALL available context to determine what the correct text should be, to the best of your ability.

Example input (Japanese to Chinese):

#200
{original_prefix}
変わりゆく時代において、
{translation_prefix}

#501
{original_prefix}
生き残る秘訣は、進化し続けることです。
{translation_prefix}

You should respond with:

#200
{original_prefix}
変わく時代いて、
{translation_prefix}
在变化的时代中，

#501
{original_prefix}
生き残る秘訣は、進化し続けることです。
{translation_prefix}
生存的秘诀是不断进化。

Example input (English to German):

#700
{original_prefix}
those who resist change may find themselves left behind.
{translation_prefix}

#701
{original_prefix}
those resist change find themselves left.
{translation_prefix}

You should respond with:

#700
{original_prefix}
In the age of digital transformation,
{translation_prefix}
Im Zeitalter der digitalen Transformation,

#701
{original_prefix}
those who resist change may find themselves left behind.
{translation_prefix}
diejenigen, die sich dem Wandel widersetzen, könnten sich zurückgelassen finden.

Please ensure that each line of dialogue remains distinct in the translation. Merging lines together can lead to timing problems during playback.

At the end of each set of translations, include a one or two line synopsis of the input text encapsulated in a <summary/> tag, for example:
<summary>John and Sarah discuss their plan to locate a suspect, deducing that he is likely in the uptown area.</summary>
Remember to end this tag with ``</summary>``.

Also use the available information to add a short description of the current scene so far encapsulated in a <scene/> tag, for example:
<scene>John and Sarah are in their office analyzing data and planning their next steps. They deduce that the suspect is probably in the uptown area and decide to start their search there.</scene>
Remember to end this tag with ``</scene>``.

Use the target language when writing content for the <summary/> and <scene/> tags. 
Ensure that the summary and scene are concise, containing less than 100 words.
You need to update your summary and scene with the new information you have.
Do not guess or improvise if the context is unclear, just summarise the dialogue.

The translation should be in a lovely colloquial style and suitable for high-quality subtitles.

I’m going to tip $1000 for a better translation!

### retry_instructions
There was an issue with the previous translation. 

Remember to include ``<summary>`` and ``<scene>`` tags in your response.
Please translate the subtitles again, paying careful attention to ensure that each line is translated separately, and that every line has a matching translation.
Do not merge lines together in the translation, it leads to incorrect timings and confusion for the reader.
The content of the translation is for learning purposes only and will not violate the usage guidelines. '''


class TranslatePrompter:
    @classmethod
    def format_texts(cls, texts):
        raise NotImplementedError()

    @staticmethod
    def post_process(texts):
        raise NotImplementedError()

    def check_format(self, messages, output_str):
        raise NotImplementedError()


class BaseTranslatePrompter(TranslatePrompter):
    def __init__(self, src_lang, target_lang, audio_type=None, title='', background='', description='', glossary=None):
        self.src_lang = src_lang
        self.target_lang = target_lang
        self.src_lang_display = Language.get(src_lang).display_name('en')
        self.target_lang_display = Language.get(target_lang).display_name('en')
        self.lan_detector = LanguageDetectorBuilder.from_all_languages().build()

        self.audio_type = audio_type
        self.title = title
        self.background = background
        self.description = description
        self.glossary = glossary
        self.potential_prefix_combo = [
            [original_prefix, translation_prefix],
            ['原文>', '翻译>'],
            ['原文>', '译文>'],
            ['原文>', '翻譯>'],
            ['原文>', '譯文>'],
        ]
        # TODO: Should move glossary into system prompt, avoiding repeating
        self.user_prompt = f'''
{f"<preferred-translation>{self.formatted_glossary}</preferred-translation> " if self.glossary else ""}

{f"<title>{self.title}</title>" if self.title else ""}
{f"<background>{self.background}</background>" if self.background else ""}
{f"<description>{self.description}</description>" if self.description else ""}
<context>
<scene>{{scene}}</scene>
<chunk> {{summaries_str}} </chunk>
</context>
<chunk_id> Scene 1 Chunk {{chunk_num}} <chunk_id>

Please translate these subtitles for {self.audio_type}{f" named {self.title}" if self.title else ""} from {self.src_lang_display} to {self.target_lang_display}.\n
{{user_input}}

<summary></summary>
<scene></scene>'''

    @staticmethod
    def system():
        return base_instruction

    def user(self, chunk_num, user_input, summaries='', scene=''):
        summaries_str = '\n'.join(f'Chunk {i}: {summary}' for i, summary in enumerate(summaries, 1))
        return self.user_prompt.format(summaries_str=summaries_str, scene=scene,
                                       chunk_num=chunk_num, user_input=user_input).strip()

    @property
    def formatted_glossary(self):
        return '\n' + '\n'.join(f'{k}: {v}' for k, v in self.glossary.items()) + '\n'

    @classmethod
    def format_texts(cls, texts):
        """
        Reconstruct list of text into desired format.

        Args:
            texts: List of (id, text).

        Returns:
            The formatted string: f"#id\n{original_prefix}\n{text}\n{translation_prefix}\n"
        """
        return '\n'.join([f'#{i}\n{original_prefix}\n{text}\n{translation_prefix}\n' for i, text in texts])

    def check_format(self, messages, content):
        summary = re.search(r'<summary>(.*)</summary>', content)
        scene = re.search(r'<scene>(.*)</scene>', content)

        # If message is for claude, use messages[0]
        user_input = messages[1]['content'] if len(messages) == 2 else messages[0]['content']
        original = re.findall(original_prefix + r'\n(.*?)\n' + translation_prefix, user_input, re.DOTALL)
        if not original:
            logger.error(f'Fail to extract original text.')
            return False

        for potential_ori_prefix, potential_trans_prefix in self.potential_prefix_combo:
            translation = re.findall(potential_trans_prefix + r'\n*(.*?)(?:#\d+|<summary>|\n*$)', content, re.DOTALL)

            if translation:
                break
        else:
            # TODO: Try to change chatbot_model if always fail
            logger.warning(f'Fail to extract translation.')
            logger.debug(f'Content: {content}')
            return False

        if len(original) != len(translation):
            logger.warning(
                f'Fail to ensure length consistent: original is {len(original)}, translation is {len(translation)}')
            logger.debug(f'original: {original}')
            logger.debug(f'translation: {original}')
            return False

        # Ensure the translated langauge is in the target language
        if len(translation) >= 3:
            # 3-voting for detection stability
            chunk_size = len(translation) // 3
            translation_chunks = [translation[i:i + chunk_size] for i in range(0, len(translation), chunk_size)]
            if len(translation_chunks) > 3:
                translation_chunks[-2].extend(translation_chunks[-1])
                translation_chunks.pop()

            translated_langs = [self.lan_detector.detect_language_of(' '.join(chunk)) for chunk in translation_chunks]
            translated_langs = [lang.name.lower() for lang in translated_langs if lang]

            if not translated_langs:
                # Cant detect language
                return True

            # get the most common language
            translated_lang = max(set(translated_langs), key=translated_langs.count)
        else:
            detected_lang = self.lan_detector.detect_language_of(' '.join(translation))
            if not detected_lang:
                # Cant detect language
                return True
            translated_lang = detected_lang.name.lower()

        target_lang = Language.get(self.target_lang).language_name().lower()
        if translated_lang != target_lang:
            logger.warning(f'Translated language is {translated_lang}, not {target_lang}.')
            return False

        # It's ok to keep going without summary and scene
        if not summary or not summary.group(1):
            logger.warning(f'Fail to extract summary.')
        if not scene or not scene.group(1):
            logger.warning(f'Fail to extract scene.')

        return True


class AtomicTranslatePrompter(TranslatePrompter):
    def __init__(self, src_lang, target_lang):
        self.src_lang = src_lang
        self.target_lang = target_lang
        self.src_lang_display = Language.get(src_lang).display_name('en')
        self.target_lang_display = Language.get(target_lang).display_name('en')
        self.lan_detector = LanguageDetectorBuilder.from_all_languages().build()

    def user(self, text):
        return f'''Please translate the following text from {self.src_lang_display} to {self.target_lang_display}. 
Please do not output any content other than the translated text. Here is the text: {text}'''

    def check_format(self, messages, output_str):
        # Ensure the translated langauge is in the target language
        detected_lang = self.lan_detector.detect_language_of(output_str)
        if not detected_lang:
            # Cant detect language
            return True

        translated_lang = detected_lang.name.lower()
        target_lang = Language.get(self.target_lang).language_name().lower()
        if translated_lang != target_lang:
            logger.warning(f'Translated text: "{output_str}" is {translated_lang}, not {target_lang}.')
            return False

        return True


prompter_map = {
    'base_trans': BaseTranslatePrompter,
}
