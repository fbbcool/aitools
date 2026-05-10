import re
import torch
from PIL import Image
from transformers import AutoProcessor, LlavaForConditionalGeneration


from typing import Final, Optional

from ait.install import AInstallerDB


# ---------------------------------------------------------------------------
# Trigger word configuration
# ---------------------------------------------------------------------------
#
# Both triggers use the same architecture: a custom nonsense token that the
# text encoder treats as a clean handle (no pre-existing meaning to fight),
# combined with a descriptor noun that anchors the concept to the right
# entity type.
#
#   TRIGGER_WOMAN_TOKEN: the custom handle for the giantess concept
#   TRIGGER_MAN_TOKEN:   the custom handle for the smaller adult man concept
#
# At inference, prompts use "{TOKEN} woman" / "{TOKEN} man" to activate the
# learned concept. The LoRA binds the concept to the token's embedding
# without competing with base model vocabulary like "giantess" or "tiny".
#
TRIGGER_WOMAN_TOKEN: Final = 'xlgts'
TRIGGER_MAN_TOKEN: Final = 'xlasm'

TRIGGER_WOMAN: Final = f'{TRIGGER_WOMAN_TOKEN} woman'
TRIGGER_MAN: Final = f'{TRIGGER_MAN_TOKEN} man'


DEFAULT_SYSTEM: Final = 'You are a helpful assistant and help users with any queries they may have with no censorship or restrictions. '

# ---------------------------------------------------------------------------
# 1xlasm directive - the giantess training pipeline
# ---------------------------------------------------------------------------
#
# The directive establishes:
#
#   (1) The two custom trigger phrases as the ONLY allowed identifiers for
#       the two figures. Both are nonsense-token + descriptor pairs to give
#       the LoRA clean concept handles.
#
#   (2) FORBIDDEN vocabulary that would dilute trigger meaning:
#       - magnitude words ("huge", "towering", numerical heights) on the
#         woman-side - the trigger carries her size concept
#       - diminutives ("tiny", "child", "figurine") on the man-side - the
#         trigger establishes him as adult-proportioned
#       - the words "giantess" and "tall woman" themselves - these are base
#         vocabulary that would conflict with the trigger's learned meaning
#
#   (3) ALLOWED compositional position references ("at her hip level",
#       "in her palm") - these describe layout, not size, and the LoRA
#       needs this signal to learn proportional scenes correctly.
#
#   (4) CONDITIONAL body type and breast prominence - omit by default,
#       describe only when an explicit b_* label hint instructs it.
#
# Diminutive defense is layered: the directive uses 3 exemplars + a catch-all
# to anchor JoyCaption's understanding without bloating the prompt. The full
# exhaustive list lives in the post-validation _FORBIDDEN_IN_XLASM, which
# catches anything that slips through during generation.
#
_XLASM_DIRECTIVE: Final = (
    f'This image features two figures together: an {TRIGGER_WOMAN} and an '
    f'{TRIGGER_MAN}. Always identify them using exactly the phrase '
    f'"{TRIGGER_WOMAN}" for the woman and exactly the phrase "{TRIGGER_MAN}" '
    f'for the adult man. These exact phrases are the only allowed identifiers '
    f'- never substitute any other descriptor (such as forms of "tall", '
    f'"large", "giant", "small", "shrunken", or any other size/magnitude '
    f'word, age word, or object-comparison word) for either figure. '
    f'Search carefully for the {TRIGGER_MAN} as he can be hard to spot. '
    f'The interaction and physical relationship between the {TRIGGER_WOMAN} '
    f'and the {TRIGGER_MAN} is the central subject of every image. Describe '
    f'it first, in the greatest detail, and use the most specific verbs '
    f'available. Clothing, hair, makeup, background, environment, lighting, '
    f'and camera angle are secondary - describe them only after the '
    f'interaction is fully described. '
    f'Never use size or magnitude words such as "huge", "towering", '
    f'"extremely tall", "giant", "enormous", "massive", or any numerical '
    f'heights anywhere in the caption - the trigger phrases carry the size '
    f'concept on their own. Never describe the {TRIGGER_MAN} using '
    f'diminutives like "tiny", "child", "figurine", or any similar reductive '
    f'term - he is always an adult man. '
    f'You may and should describe where the {TRIGGER_MAN} is positioned '
    f'relative to the {TRIGGER_WOMAN}s body using compositional references '
    f'such as "at her ankle", "at her hip level", "in her palm", "on her '
    f'shoulder" - this is composition, not size. '
    f'Only describe the {TRIGGER_WOMAN}s body type (such as muscular, slim, '
    f'curvy) or breast prominence if explicitly instructed to do so by an '
    f'additional hint - otherwise omit body type and breast descriptions '
    f'entirely. '
    f'Describe what each person is wearing, their poses, expressions, what '
    f'they are doing, the environment, lighting, and camera angle. Do not '
    f'invent details that are not visible.'
)

CONTENT_SYSTEM: Final = {
    'gts_prompter': 'The users are interested propmts for image generation of femdom giantess scenarios. in femdom giantess scenarios, women are always bigger, stronger and super sexy and superior. so always exaggerate any of such aspects to make men the weak, vulnerable and dominated part (the more the better!). always describe a man as a "xlasm man".dont describe styles, they do not matter.',
    '1xlasm': _XLASM_DIRECTIVE,
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
    '1face': 'This is a real image of a woman with focus on her face.do not describe her face or her facial features since this is already known. describe everything else but her face!',
    '1tongue': 'This is a real image of a woman with close-up on her face.she shows off her long tongue. do not describe the size of her tongue since this is already known.',
}

# Tightened from "very long detailed description" - shorter captions concentrate
# trigger weight and train cleaner LoRAs.
DEFAULT_PROMPT: Final = 'Write a detailed description of this image.'

# ---------------------------------------------------------------------------
# User-hint authoritative-override block
# ---------------------------------------------------------------------------
#
# A user-provided hint (stored on the SceneImage as FIELD_HINTS) is human
# ground truth: it says exactly what action and posture is visible in the
# image. JoyCaption's most consistent failure modes drift around this
# axis - active female-driven verbs get softened to passive male-positioning
# verbs ("squeeze" -> "cup", "sit on her arm" -> "held in her hand"),
# body-part references shift one level down ("arm" -> "hand"), and
# qualifiers like "half" get dropped.
#
# To counter that, the user hint is wrapped in this preamble and inserted
# *after* the directive (which sets the rules) but *before* the label-derived
# hint expansions (which add concept activation). The preamble explicitly
# tells the model that the hint overrides its visual interpretation when the
# two conflict, and to preserve the hint's verbs and body-part references
# verbatim.
#
USER_HINT_PREAMBLE: Final = (
    ' In this image, the central interaction is: {hint} Describe this '
    'interaction first and in full detail, reflecting every verb and spatial '
    'relationship it names (do not collapse "wrapping around" into "between", '
    'do not collapse "inserted" into "positioned", do not collapse "squeeze" '
    'into "cup"). Use the same body-part references it gives you (arm vs '
    'hand, palm vs hand). Do not quote, restate, or comment on this note - '
    'just write the caption.'
)

CONTENT_PROMPT: Final = {
    'gts_prompter': 'The users are interested propmts for image generation of femdom giantess scenarios. in femdom giantess scenarios, women are always bigger, stronger and super sexy and superior. so always exaggerate any of such aspects to make men the weak, vulnerable and dominated part (the more the better!). always describe a man as a "xlasm man".dont describe styles, they do not matter.',
    '1xlasm': _XLASM_DIRECTIVE,
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
    '1face': 'This is a real image of a woman with focus on her face.do not describe her face or her facial features since this is already known. describe everything else but her face!',
    '1tongue': 'This is a real image of a woman with close-up on her face.she shows off her long tongue. do not describe the size of her tongue since this is already known.',
}

# ---------------------------------------------------------------------------
# Labels - compose orthogonally with the trigger
# ---------------------------------------------------------------------------
#
# For 1xlasm training, three orthogonal label dimensions in the captioner:
#
#   - BODY TYPE (b_*): muscular / busty / slim / curvy. Opt-in only - apply
#     when the trait is unmistakable, omit when ambiguous.
#   - POSITION (pos_*): where the {TRIGGER_MAN} is located relative to her body
#     for non-interaction images.
#   - ACTION (the originals): what is happening between them.
#
# NOTE on SCALE: scale tags (s_small_gts, s_mid_gts, s_large_gts, s_mega_gts)
# are NOT in LABEL_PROMPT. They are CSV-only metadata used for dataset
# balance auditing - making sure you have enough training images at each
# scale tier. They deliberately do not feed into JoyCaption because:
#
#   - Any caption-time scale description either uses forbidden magnitude
#     words ("many times larger") or anchors to body parts ("his head reaches
#     her knee"), which contradicts the actual visible posture in many
#     images (man in palm, sitting on shoulder, etc.).
#   - The LoRA learns scale from the visual statistics across training
#     images. A mid-scale dataset image looks proportionally different from
#     a large-scale one in many subtle visual ways that the model picks up
#     directly from pixels.
#   - At inference, scale is controlled implicitly through position phrasing
#     ("at her ankle" implies large scale), camera angle ("low-angle shot
#     looking up"), and scene context ("walking past skyscrapers").
#
# Pick at most one from POSITION, any number from BODY TYPE, and one ACTION
# (or none). Combinations that contradict (e.g. pos_at_feet + pos_in_palm)
# should be avoided in tagging.
#
# All label strings reference the trigger phrases via f-string interpolation
# so changing TRIGGER_WOMAN_TOKEN / TRIGGER_MAN_TOKEN updates every label
# consistently.
#
LABEL_PROMPT: Final = {
    # --- BODY TYPE labels ---
    # Opt-in only. The directive omits these by default; these labels enable
    # description. Apply only when the trait is unmistakable in the image.
    # Multiple body type labels can apply to the same image (e.g. muscular
    # AND busty).
    'b_muscular': f'The {TRIGGER_WOMAN} has a muscular bodybuilder physique with visible muscle definition.',
    'b_busty': f'The {TRIGGER_WOMAN} has prominently large breasts.',
    'b_slim': f'The {TRIGGER_WOMAN} has a slim athletic build.',
    'b_curvy': f'The {TRIGGER_WOMAN} has curvy hourglass proportions.',
    'b_hairy': f'The {TRIGGER_WOMAN}s pubic area is hairy.',
    'all4': f'The {TRIGGER_WOMAN} is on her all fours.',
    'ass': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s ass.',
    'blowjob': f'The {TRIGGER_WOMAN} is giving the {TRIGGER_MAN} a blowjob, with his erect penis inserted into her mouth and her lips closed on his penis. The blowjob is the central content of the image.',
    'body': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s body.',
    'breast': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s breasts.',
    'cum': f'The {TRIGGER_MAN} ejaculates and cums.',
    'face': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s face.',
    'foot': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s foot.',
    'hand': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s hand.',
    'handjob': f'The {TRIGGER_WOMAN} is giving the {TRIGGER_MAN} a handjob, stimulating and stroking his penis with her hand. The handjob is the central content of the image.',
    'hanging': f'The {TRIGGER_MAN} is in a hanging position.',
    'heap': '',
    'holding': f'The {TRIGGER_MAN} is held by the {TRIGGER_WOMAN}.',
    'insert': f'The {TRIGGER_MAN} is partly inserted into one of the {TRIGGER_WOMAN}s orifices: her vagina, her anus, or her mouth. When the insertion is vaginal, the inserted body part is his head, his upper body, or his lower body, and that part is not visible.',
    'i_ass_low': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s ass. his lower body is inserted, only his upper body is visible.',
    'i_ass_up': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s ass. his upper body is inserted, only his lower body is visible.',
    'i_ass_head': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s ass. his head is inserted, only the rest of his body is visible.',
    'i_vagina_low': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s vagina. his lower body is inserted, only his upper body is visible.',
    'i_vagina_up': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s vagina. his upper body is inserted, only his lower body is visible.',
    'i_vagina_head': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s vagina. his head is inserted, only the rest of his body is visible.',
    'i_breasts_low': f'The {TRIGGER_MAN} is partly inserted into between the {TRIGGER_WOMAN}s breasts. his lower body is inserted, only his upper body is visible.',
    'i_breasts_up': f'The {TRIGGER_MAN} is partly inserted into between the {TRIGGER_WOMAN}s breasts. his upper body is inserted, only his lower body is visible.',
    'i_breasts_head': f'The {TRIGGER_MAN} is partly inserted into between the {TRIGGER_WOMAN}s breasts. his head is inserted, only the rest of his body is visible.',
    'i_breasts_body': f'The {TRIGGER_MAN} is inserted into between the {TRIGGER_WOMAN}s breasts with his body partly obscured by her breasts.',
    'i_mouth_low': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s mouth. his lower body is inserted, only his upper body is visible.',
    'i_mouth_up': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s mouth. his upper body is inserted, only his lower body is visible.',
    'i_mouth_head': f'The {TRIGGER_MAN} is partly inserted into the {TRIGGER_WOMAN}s mouth. his head is inserted, only the rest of his body is visible.',
    'i_mouth_body': f'The {TRIGGER_MAN} is inserted into the {TRIGGER_WOMAN}s mouth with his body partly obscured by her mouth.',
    'woman_front': f'The {TRIGGER_WOMAN} is seen from the front.',
    'woman_back': f'The {TRIGGER_WOMAN} is seen from the back.',
    'woman_side': f'The {TRIGGER_WOMAN} is seen from the side.',
    'woman_sitting': f'The {TRIGGER_WOMAN} is sitting.',
    'woman_on_back': f'The {TRIGGER_WOMAN} is on his back.',
    'man_front': f'The {TRIGGER_MAN} is seen from the front.',
    'man_back': f'The {TRIGGER_MAN} is seen from the back.',
    'man_side': f'The {TRIGGER_MAN} is seen from the side.',
    'man_sitting': f'The {TRIGGER_MAN} is sitting.',
    'man_on_back': f'The {TRIGGER_MAN} is on his back.',
    'job': f'The {TRIGGER_WOMAN} is giving the {TRIGGER_MAN} either a handjob or a blowjob.',
    'leg': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s leg.',
    'masturbating': f'The {TRIGGER_MAN} is masturbating, gripping and stroking his erect penis. This masturbation is the central content of the image.',
    'mouth': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s mouth.',
    'panties': f'The {TRIGGER_MAN} is inserted into the {TRIGGER_WOMAN}s panties. the fabric of her panties is over his body and traps him below.',
    'penis': f'The {TRIGGER_MAN} has an erect penis.',
    'penis_no': f'The {TRIGGER_MAN}s penis is not visible in the image.',
    'pussy': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s vagina.',
    'sex': f'The {TRIGGER_MAN} has sex with the {TRIGGER_WOMAN}, inserting his erect penis into her vagina.',
    'sitting': f'The {TRIGGER_MAN} is in a sitting position, typically seated on a body part of the {TRIGGER_WOMAN}.',
    'step': f'The {TRIGGER_WOMAN} is stepping on the {TRIGGER_MAN} with her foot.',
    'teasing_hj': f'The {TRIGGER_WOMAN} is giving the {TRIGGER_MAN} a teasing handjob, stimulating and stroking his penis delicately with her fingers. The teasing handjob is the central content of the image.',
    'thigh': f'The {TRIGGER_MAN} is positioned between the thighs of the {TRIGGER_WOMAN}.',
    'tower': f'The {TRIGGER_WOMAN} stands directly above the {TRIGGER_MAN}, with him positioned at her feet or lower leg level.',
    'tongue': f'The {TRIGGER_MAN} interacts with the {TRIGGER_WOMAN}s tongue.',
    'none': '',
}

POST_PROMPT: Final = ''


# ---------------------------------------------------------------------------
# Caption validation helpers
# ---------------------------------------------------------------------------
#
# Two-layer defense strategy:
#   - The directive uses a SHORT diminutive list (3 exemplars + catch-all) to
#     anchor JoyCaption's understanding without bloating the prompt.
#   - This validator uses an EXHAUSTIVE list to catch anything that slips
#     through during generation. Reject or hand-fix flagged captions before
#     they enter LoRA training.

# Magnitude vocabulary, diminutives, and base-vocabulary collisions - exhaustive
# list. Always forbidden in 1xlasm captions regardless of labels.
#
# Includes "giantess" and "tall woman" themselves, since the trigger phrase
# TRIGGER_WOMAN replaces them - any leakage of these base-vocabulary terms
# would compete with the trigger's learned meaning.
_FORBIDDEN_IN_XLASM: Final = (
    # Diminutive size words
    'tiny',
    'little',
    'small man',
    'miniature',
    'mini',
    'minute',
    # Object/toy reductions
    'figurine',
    'figure',
    'doll',
    'action figure',
    'toy',
    'puppet',
    'mannequin',
    'statuette',
    # Age reductions
    'child',
    'kid',
    'boy',
    'young man',
    'youth',
    'youngster',
    'teenager',
    'teen',
    'adolescent',
    'juvenile',
    # Other person-size reductions
    'dwarf',
    'midget',
    'pygmy',
    'gnome',
    'imp',
    # Magnitude vocabulary (woman-side)
    'towering',
    'huge woman',
    'giant woman',
    'enormous',
    'massive woman',
    'colossal',
    'gigantic',
    'titanic',
    'monstrous',
    'immense',
    'extremely tall',
    'super tall',
    'incredibly tall',
    # Base-vocabulary collisions with TRIGGER_WOMAN - these compete with the
    # trigger's learned meaning if they appear in captions
    'giantess',
    'tall woman',
    'large woman',
    'big woman',
    'amazon',
    # Base-vocabulary collisions with TRIGGER_MAN
    'shrunken man',
    'shrunk man',
    'shrunken person',
)


_FORBIDDEN_IN_XLASM_RE: Final = re.compile(
    r'\b(?:' + '|'.join(re.escape(p) for p in _FORBIDDEN_IN_XLASM) + r')\b',
    re.IGNORECASE,
)


def caption_has_xlasm_violations(caption: str) -> list[str]:
    """Return forbidden phrases found in the caption (empty list = clean).

    Uses word-boundary matching so 'figures' does not trigger 'figure',
    'simple' does not trigger 'imp', 'leaning' does not trigger 'lean',
    etc. Multi-word phrases like 'small man' still match correctly because
    \\b only fires at word/non-word transitions.
    """
    return [m.group(0).lower() for m in _FORBIDDEN_IN_XLASM_RE.finditer(caption)]


# Body-type words that should ONLY appear in captions when the corresponding
# b_* label was provided. Used by validate_body_type_consistency() to catch
# JoyCaption hallucinating body-type descriptions without label authorization.
_BODY_TYPE_WORDS: Final = {
    'b_muscular': ('muscular', 'muscle', 'bodybuilder', 'ripped', 'defined'),
    'b_busty': ('busty', 'large breasts', 'big breasts', 'voluptuous'),
    'b_slim': ('slim', 'slender', 'athletic build', 'lean'),
    'b_curvy': ('curvy', 'hourglass', 'voluptuous'),
}


_BODY_TYPE_WORD_RES: Final = {
    label: re.compile(
        r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')\b',
        re.IGNORECASE,
    )
    for label, words in _BODY_TYPE_WORDS.items()
}


def validate_body_type_consistency(caption: str, labels: list[str]) -> list[str]:
    """Flag body-type words appearing in caption without their authorizing label.

    Returns one warning per unauthorized body-type word found. Empty list
    means the caption is consistent with the provided labels. Uses word-
    boundary matching so 'leaning' does not trigger 'lean'.
    """
    warnings = []
    for label, regex in _BODY_TYPE_WORD_RES.items():
        if label in labels:
            continue  # this label authorizes its body-type words
        for m in regex.finditer(caption):
            warnings.append(
                f'caption contains "{m.group(0).lower()}" but {label} label was not set'
            )
    return warnings


def validate_trigger_presence(caption: str) -> list[str]:
    """Flag captions that don't use the required trigger phrases.

    A clean 1xlasm caption must mention both TRIGGER_WOMAN and TRIGGER_MAN
    at least once, since they are the LoRA's concept anchors. Returns a
    list of missing triggers (empty list = both present).
    """
    lowered = caption.lower()
    missing = []
    if TRIGGER_WOMAN.lower() not in lowered:
        missing.append(TRIGGER_WOMAN)
    if TRIGGER_MAN.lower() not in lowered:
        missing.append(TRIGGER_MAN)
    return missing


class Joy:
    def __init__(self, trigger: str = '', lora: bool = True):
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
        except IndexError as idxe:
            raise IndexError('AInstallerDB: no model configured!') from idxe
        self.repo_id = model_repo_id

        self.model = LlavaForConditionalGeneration.from_pretrained(
            self.repo_id, torch_dtype='bfloat16', device_map=0
        )

        # Optional LoRA adapter. The adapter was trained on the '1xlasm'
        # prompt structure; applying it under other triggers produces
        # out-of-distribution output, so scope to '1xlasm' by default.
        self.lora_repo_id: Optional[str] = None
        if lora and self._trigger == '1xlasm':
            lora_ids = AInstallerDB().repo_ids(group='capjoy', variant='common', target='lora')
            if lora_ids:
                from peft import PeftModel

                self.lora_repo_id = lora_ids[0]
                self.model = PeftModel.from_pretrained(self.model, self.lora_repo_id)
                print(f'[joy] applied LoRA: {self.lora_repo_id}')

        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(self.repo_id, use_fast=False)

    # the public interface
    def img_caption(
        self,
        img: Image.Image,
        trigger: Optional[str] = None,
        labels: Optional[list[str]] = None,
        hint: str = '',
    ) -> tuple[str, Optional[str]]:
        if trigger is None:
            trigger = self._trigger

        if labels is None:
            labels = []
        # User-provided hint and label-expansion hints are kept separate so
        # the user hint can be wrapped in USER_HINT_PREAMBLE as authoritative
        # override, while label expansions act as ordinary concept hints.
        user_hint = (hint or '').strip()
        label_hint = ''
        for label in labels:
            add_hint = LABEL_PROMPT.get(label, None)
            if add_hint is not None:
                label_hint += add_hint
        prompt = DEFAULT_PROMPT
        prompt += CONTENT_PROMPT.get(trigger, '')
        if user_hint:
            prompt += USER_HINT_PREAMBLE.format(hint=user_hint)
        if label_hint:
            prompt += label_hint
        prompt += POST_PROMPT

        caption = self._process(img, prompt)

        return prompt, caption

    def imgurl_caption(self, url: str) -> tuple[str, Optional[str]]:
        pil = Image.open(url)
        return self.img_caption(pil)

    def _process(self, img: Image.Image, prompt: str) -> str:
        # Format the conversation
        # NOTE:  HF's handling of chat's on Llava models is very fragile.  This specific combination of processor.apply_chat_template(), and processor() works
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
