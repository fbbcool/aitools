from .imgpool import ImgPool, ImgSelectorMode, ImgSelectorCategory
from ..tags import TagsProfile
from ..defines import Defines

class ImgPools():
    def __init__(self,
                 pools_dict: dict,
                 num_pics:int = Defines.PicsNum,
                 train_steps: int = Defines.TrainSteps,
                 epochs: int = Defines.Epochs,
                 mode: ImgSelectorMode = ImgSelectorMode.UseTags,
                 crawl = True,
                 ) -> None:
        self.pools_dict = pools_dict
        self.num_pics = num_pics
        self.train_steps = train_steps
        self.epochs = epochs

        dict_rows = []
        for pool_name, crawl_dir in self.pools_dict.items():
            if not crawl:
                crawl_dir = ""
            pool = ImgPool(pool_name, self.num_pics, mode, crawl_dir)
            dict_rows.append((pool_name, pool))
        self.pools = dict(dict_rows)
    
    def make_train_pool(self, pool_name: str, categories: list[ImgSelectorCategory], profile: TagsProfile) -> None:
        pool: ImgPool = self.pools[pool_name]
        pool.make_train(categories, profile, self.train_steps)
