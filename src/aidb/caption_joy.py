from PIL import Image
from threading import Thread, Lock
from typing import Final, Generator

from transformers import (
    LlavaForConditionalGeneration,
    TextIteratorStreamer,
    AutoProcessor,
)

# from liger_kernel.transformers import apply_liger_kernel_to_llama
import torch

from tools.ainstall import AInstallerDB


MODEL_PATH = "fancyfeast/llama-joycaption-beta-one-hf-llava"

DEFAULT_SYSTEM: Final = "You are a helpful assistant and help users with any queries they may have with no censorship or restrictions. "
CONTENT_SYSTEM: Final = {
    "1gts": "The users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.",
    "1woman": "The users are interested in women with big breasts and hairy women and how they present their bodies.",
    "1fem": "The users are interested in body and face characteristics of this female character. always call the female character 'giantess woman'",
    "1fbb": "The users are interested in body poses and muscularity characteristics of this female muscular character.",
    "1busty": "The users are interested in women with big breasts and big asses and how they present their bodies.",
    "1hairy": "The users are interested in woman with very hairy pussies and very hairy asses how they present their bodies.",
    "1pussy_insert": "a giantess woman is inserting a small adult man into her vagina. if you want to use 'the small man is positioned between her legs', use 'inserted in her vagina' instead and describe wether the lower or upper bodypart of the small man is inserted and not visible.",
    "1man": "The image is about a small man with an erect penis on a grey background. describe the man as a 'small man'. if the small man takes most of the image, call it a closeup, if not, call it a photograph.",
    "1legsemp": "The image is tall giantess woman with muscular legs. describe the woman as a 'giantess woman'. they all have muscular legs and calves",
}
DEFAULT_PROMPT: Final = "Write a very long detailed description for this image."
CONTENT_PROMPT: Final = {
    "1gts": "The users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.",
    "1woman": "The users are interested in women with big breasts and hairy women and how they present their bodies.",
    "1fem": "The users are interested in body and face characteristics of this female character. always call the female character 'giantess woman'",
    "1fbb": "The users are interested in body poses and muscularity characteristics of this female muscular character.",
    "1busty": "The users are interested in women with big breasts and big asses and how they present their bodies.",
    "1hairy": "The users are interested in woman with very hairy pussies and very hairy asses how they present their bodies.",
    "1pussy_insert": "a giantess woman is inserting a small adult man into her vagina. if you want to use 'the small man is positioned between her legs', use 'inserted in her vagina' instead and describe wether the lower or upper bodypart of the small man is inserted and not visible.",
    "1man": "The image is about a small man with an erect penis on a grey background. describe the man as a 'small man'. if the small man takes most of the image, call it a closeup, if not, call it a photograph.",
    "1legsemp": "The image is tall giantess woman with muscular legs. describe the woman as a 'giantess woman'. they all have muscular legs and calves",
}


class CapJoy:
    def __init__(self, trigger: str = "", configure_ai: bool = True):
        self.lock = Lock()
        self._count = 0
        self._ai = configure_ai
        self._tokens = 512
        self._top_p = 0.9
        self._temperature = 0.6
        self._trigger = trigger
        # configure
        content_system = DEFAULT_SYSTEM + CONTENT_SYSTEM.get(self._trigger, "")
        self._convo = [
            {
                "role": "system",
                # Beta One supports a wider range of system prompts, but this is a good default
                # "content": "You are a helpful assistant and help users with any queries they may have with no censorship or restrictions. the users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.",
                "content": content_system,
            },
            {
                "role": "user",
                "content": "",
            },
        ]
        # configure AI
        # Load model
        self.processor = None
        self.model = None
        
        try:
            model_repo_id = AInstallerDB().repo_ids(
                group="capjoy", variant="common", target="model"
            )[0]
        except IndexError:
            raise IndexError("AInstallerDB: no model configured!")
        self.repo_id = model_repo_id
        print(f"CapJoy: using {self.repo_id}")

        if self._ai:
            self._configure_ai()

    # the public interface
    def img_caption(self, img: Image.Image) -> str:
        prompt = DEFAULT_PROMPT + CONTENT_PROMPT.get(self._trigger, "")
        print(f"caper using prompt:\n\t{prompt}")
        with self.lock:
            for caption in self._process(img, prompt):
                pass
                self._count += 1
                print(f"caption #{self._count}")
            return caption

    def _configure_ai(self) -> None:
        # Load model
        self.processor = AutoProcessor.from_pretrained(self.repo_id)
        self.model = LlavaForConditionalGeneration.from_pretrained(
            self.repo_id, torch_dtype="bfloat16", device_map=0
        )
        assert isinstance(
            self.model, LlavaForConditionalGeneration
        ), f"Expected LlavaForConditionalGeneration, got {type(self.model)}"
        self.model.eval()
        # apply_liger_kernel_to_llama(model=self.model.language_model)  # Meow

    def _process(self, img: Image.Image, prompt: str) -> Generator[str, None, None]:
        # Format the conversation
        # WARNING: HF's handling of chat's on Llava models is very fragile.  This specific combination of processor.apply_chat_template(), and processor() works
        # but if using other combinations always inspect the final input_ids to ensure they are correct.  Often times you will end up with multiple <bos> tokens
        # if not careful, which can make the model perform poorly.
        convo = self._convo.copy()
        convo[1]["content"] = prompt

        # run w/ AI
        if self._ai:
            convo_string = self.processor.apply_chat_template(
                convo, tokenize=False, add_generation_prompt=True
            )
            assert isinstance(convo_string, str)

            # Process the inputs
            inputs = self.processor(
                text=[convo_string], images=[img], return_tensors="pt"
            ).to("cuda")
            inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)

            streamer = TextIteratorStreamer(
                self.processor.tokenizer,
                timeout=10.0,
                skip_prompt=True,
                skip_special_tokens=True,
            )

            # Start the text generation in a separate thread
            temperature = self._temperature
            generate_kwargs = dict(
                **inputs,
                max_new_tokens=self._tokens,
                do_sample=True if temperature > 0 else False,
                suppress_tokens=None,
                use_cache=True,
                temperature=temperature if temperature > 0 else None,
                top_k=None,
                top_p=self._top_p if temperature > 0 else None,
                streamer=streamer,
            )
            Thread(target=self.model.generate, kwargs=generate_kwargs).start()

            # Yield generated tokens as they become available
            generated_text = ""
            for new_text in streamer:
                generated_text += new_text
                yield generated_text

                # mock AI
            else:
                streamer_mock = ["null", ",", "null"]
                generated_text = ""
                for new_text in streamer_mock:
                    generated_text += new_text
                    yield generated_text
