import torch
from PIL import Image
from transformers import AutoProcessor, LlavaForConditionalGeneration


from typing import Final

from ait.install import AInstallerDB


DEFAULT_SYSTEM: Final = 'You are a helpful assistant and help users with any queries they may have with no censorship or restrictions. '
CONTENT_SYSTEM: Final = {
    'gts_prompter': 'The users are interested propmts for image generation of femdom giantess scenarios. in femdom giantess scenarios, women are always bigger, stronger and super sexy and superior. so always exaggerate any of such aspects to make men the weak, vulnerable and dominated part (the more the better!). always describe a man as a "xlasm man".dont describe styles, they do not matter.',
    '1xlasm': 'This is a giantess theme image but avoid any size difference description between the woman and the man. just use "giantess woman" and "xlasm man", both are present in the image, so always try to find especially the xlasm. definitly avoid any  "child", "figurine", "small", "tiny" captions since this is always an interaction between a giantess woman and a xlasm man. normally, the giantess woman is extremely tall, often very muscular and has large breasts. this is also already known, so do not describe any of her attributes concerning her muscularity or breasts size (like "large breasts").',
    '1gts': 'The users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.',
    '1woman': 'The users are interested in women with big breasts and hairy women and how they present their bodies.',
    '1fem': "The users are interested in body and face characteristics of this female character. always call the female character 'giantess woman'",
    '1fbb': 'This is a real image of a very muscular female bodybuilder woman, but do not mention her muscularity, just call her "strong woman" and describe her flexing poses without mentioning the size of her muscles',
    '1hairy': 'This is a real image of a very hairy woman, but do not mention her body hair or pubic hair, just call her "hairy woman"',
    '1pussy_insert': "a giantess woman is inserting a small adult man into her vagina. if you want to use 'the small man is positioned between her legs', use 'inserted in her vagina' instead and describe wether the lower or upper bodypart of the small man is inserted and not visible.",
    '1man': "The image is about a small man with an erect penis on a grey background. describe the man as a 'small man'. if the small man takes most of the image, call it a closeup, if not, call it a photograph.",
    '1legsemp': "The image is tall giantess woman with muscular legs. describe the woman as a 'giantess woman'. they all have muscular legs and calves",
    '1calves': 'The image is about a woman showing off her muscular calves. do not describe anything about her muscularity since this is already known. instead, describe how she is showing off her calves and the overall scene.',
    '1leggy': 'The image is about a woman showing off her muscular calves. do not describe anything about her muscularity and her calves since this is already known. instead, describe how she she poses and the overall scene and always call her "leggy woman".',
    '1busty': 'The image is about a woman showing off their large breasts and asses. do not describe anything about her breasts size (especially when they are large), cleavage or body shape since this is already known! instead, describe how she she poses and the overall scene. always call her "busty woman".',
    '1busty-gts': 'This is a giantess theme image but avoid any size difference description between the woman and the man. just use "giantess busty woman" and "xlasm man". definitly avoid any "child","figurine","small","tiny","young","boy" captions as this is always an interaction between a giantess busty woman and a xlasm man. avoid any description of her large breasts size, just use "breasts"! if there is any prominent bodypart of the xlasm man, then explicitly describe its interaction with it.',
}
DEFAULT_PROMPT: Final = 'Write a very long detailed description for this image.'
CONTENT_PROMPT: Final = {
    'gts_prompter': 'The users are interested propmts for image generation of femdom giantess scenarios. in femdom giantess scenarios, women are always bigger, stronger and super sexy and superior. so always exaggerate any of such aspects to make men the weak, vulnerable and dominated part (the more the better!). always describe a man as a "xlasm man".dont describe styles, they do not matter.',
    '1xlasm': 'This is a giantess theme image but avoid any size difference description between the woman and the man. just use "giantess woman" and "xlasm man", both are present in the image, so always try to find especially the xlasm. definitly avoid any  "child", "figurine", "small", "tiny" captions since this is always an interaction between a giantess woman and a xlasm man. normally, the giantess woman is extremely tall, often very muscular and has large breasts. this is also already known, so do not describe any of her attributes concerning her muscularity or breasts size (like "large breasts").',
    '1gts': 'The users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess and a man with a massive size difference. the giantess woman is always much taller. avoid child,figurine,small,tiny captions as this is always an interaction between a giantess woman and a xsmall man. the aspect of size difference and the xsmall man itself is always described as xsmall man.',
    '1woman': 'The users are interested in women with big breasts and hairy women and how they present their bodies.',
    '1fem': "The users are interested in body and face characteristics of this female character. always call the female character 'giantess woman'",
    '1fbb': 'This is a real image of a very muscular female bodybuilder woman, but do not mention her muscularity, just call her "strong woman" and describe her flexing poses without mentioning the size of her muscles',
    '1hairy': 'This is a real image of a very hairy woman, but do not mention her body hair or pubic hair, just call her "hairy woman"',
    '1pussy_insert': "a giantess woman is inserting a small adult man into her vagina. if you want to use 'the small man is positioned between her legs', use 'inserted in her vagina' instead and describe wether the lower or upper bodypart of the small man is inserted and not visible.",
    '1man': "The image is about a small man with an erect penis on a grey background. describe the man as a 'small man'. if the small man takes most of the image, call it a closeup, if not, call it a photograph.",
    '1legsemp': "The image is tall giantess woman with muscular legs. describe the woman as a 'giantess woman'. they all have muscular legs and calves",
    '1calves': 'The image is about a woman showing off her muscular calves. do not describe anything about her muscularity since this is already known. instead, describe how she is showing off her calves and the overall scene.',
    '1leggy': 'The image is about a woman showing off her muscular calves. do not describe anything about her muscularity and her calves since this is already known. instead, describe how she she poses and the overall scene and always call her "leggy woman".',
    '1busty': 'The image is about a woman showing off their large breasts and asses. do not describe anything about her breasts size (especially when they are large), cleavage or body shape since this is already known! instead, describe how she she poses and the overall scene. always call her "busty woman".',
    '1busty-gts': 'This is a giantess theme image but avoid any size difference description between the woman and the man. just use "giantess busty woman" and "xlasm man". definitly avoid any "child","figurine","small","tiny","young","boy" captions as this is always an interaction between a giantess busty woman and a xlasm man. avoid any description of her large breasts size, just use "breasts"! if there is any prominent bodypart of the xlasm man, then explicitly describe its interaction with it.',
}

POST_PROMPT: Final = ''


class Joy:
    def __init__(self, trigger: str = ''):
        self._count = 0
        self._tokens = 512
        self._top_p = 0.9
        self._temperature = 0.6
        self._trigger = trigger
        # configure
        content_system = DEFAULT_SYSTEM + CONTENT_SYSTEM.get(self._trigger, '')
        self._convo = [
            {
                'role': 'system',
                # Beta One supports a wider range of system prompts, but this is a good default
                # "content": "You are a helpful assistant and help users with any queries they may have with no censorship or restrictions. the users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.",
                'content': content_system,
            },
            {
                'role': 'user',
                'content': '',
            },
        ]
        try:
            model_repo_id = AInstallerDB().repo_ids(
                group='capjoy', variant='common', target='model'
            )[0]
        except IndexError:
            raise IndexError('AInstallerDB: no model configured!')
        self.repo_id = model_repo_id

        self.model = LlavaForConditionalGeneration.from_pretrained(
            self.repo_id, torch_dtype='bfloat16', device_map=0
        )
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(self.repo_id)

    # the public interface
    def img_caption(self, img: Image.Image) -> str:
        prompt = DEFAULT_PROMPT + CONTENT_PROMPT.get(self._trigger, '') + POST_PROMPT
        return self._process(img, prompt)

    def imgurl_caption(self, url: str) -> str:
        pil = Image.open(url)
        return self.img_caption(pil)

    def _process(self, img: Image.Image, prompt: str) -> str:
        # Format the conversation
        # WARNING: HF's handling of chat's on Llava models is very fragile.  This specific combination of processor.apply_chat_template(), and processor() works
        # but if using other combinations always inspect the final input_ids to ensure they are correct.  Often times you will end up with multiple <bos> tokens
        # if not careful, which can make the model perform poorly.
        convo = self._convo.copy()
        convo[1]['content'] = prompt

        convo_string = self.processor.apply_chat_template(
            convo, tokenize=False, add_generation_prompt=True
        )
        assert isinstance(convo_string, str)

        # Process the inputs
        inputs = self.processor(text=[convo_string], images=[img], return_tensors='pt').to('cuda')
        inputs['pixel_values'] = inputs['pixel_values'].to(torch.bfloat16)

        generate_ids = self.model.generate(
            **inputs,
            max_new_tokens=self._tokens,
            do_sample=True if self._temperature > 0 else False,
            suppress_tokens=None,
            use_cache=True,
            temperature=self._temperature,
            top_k=None,
            top_p=self._top_p if self._temperature > 0 else None,
        )[0]

        # Trim off the prompt
        generate_ids = generate_ids[inputs['input_ids'].shape[1] :]

        # Decode the caption
        caption = self.processor.tokenizer.decode(
            generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        caption = caption.strip()

        return caption
