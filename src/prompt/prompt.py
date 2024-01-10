class Prompt:
    def __init__(self) -> None:
        pass

    @classmethod
    def reference_lora_femchar(self, lora: str, trigger: str = "", weight: float = 1.0) -> str:
        pr = f"woman standing in an opulent room,{trigger},high ceiling,high heels,full body,looking at viewer,frontal view,realistic,<lora:{lora}:{weight:.1f}>"
        return pr