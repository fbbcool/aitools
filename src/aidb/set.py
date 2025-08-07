from aidb.dbmanager import DBManager
from aidb.image import Image
from aidb.query import Query


class SetImg:
    def __init__(self, dbm: DBManager, name: str | None = None, from_dict: dict | None = None, autoload: bool = False) -> None:
        if not isinstance(dbm, DBManager):
            raise TypeError("SetImg dbm is not a DBManager!")
        
        self._dbm = dbm
        self.name = None
        self._query = Query(self._dbm)
        self._imgs: dict[str,list[Image]] = {}
        """dict of image collections and the selected imgs from the collection"""
        
        if name is not None:
            if not isinstance(name, str):
                raise TypeError("SetImg name is not a string!")
            self.name = name
            if autoload:
                from_dict = self._dbm.find_documents('sets_img', {"name": self.name})
                if not from_dict:
                    print(f"[SetImg] autoload failed: no set '{self.name}' stored!")
                    from_dict = None
                else:
                    from_dict = from_dict[0]
        
        if from_dict is not None:
            if not isinstance(from_dict, dict):
                raise TypeError("SetImg from_dict is not a dict!")
            self._from_dict(from_dict)
    
    def _from_dict(self, from_dict: dict) -> None:
        if self.name is None:
            self.name = from_dict.get("name", None)
        self._dict_to_imgs(from_dict.get("imgs", {}))
    
    @property
    def to_dict(self) -> dict:
        ret = {"name": self.name, "imgs": self._imgs_to_dict}
        return ret
    
    @property
    def _imgs_to_dict(self) -> dict:
        ret = {}
        for collection in self._imgs:
            if collection not in self._dbm.collections_images:
                continue
            ids = []
            for img in self._imgs[collection]:
                ids.append(img.id)
            ret |= {collection: ids}
        return ret

    def _dict_to_imgs(self, dict_imgs: dict) -> None:
        self._imgs = {}
        for collection in dict_imgs:
            if collection not in self._dbm.collections_images:
                continue
            imgs = []
            for id in dict_imgs[collection]:
                img = Image(self._dbm, id, collection)
                imgs.append(img)
            self._imgs |= {collection: imgs}
    
    @property
    def collections(self) -> list[str]:
        return [collection for collection in self._imgs]
    
    def add(self, imgs: Image | list [Image]):
        if not imgs:
            return
        if not isinstance(imgs, list):
            imgs = [imgs]
        
        for img in imgs:
            collection = img.collection
            if collection in self.collections:
                self._imgs[collection].append(img)
            else:
                if collection not in self._dbm.collections_images:
                    continue
                self._imgs |= {collection: [img]}
    
    def select(self, n: int, collections: dict[str,float] | list [str]):
        """
        selects n images from given collections in the range of ratings 3-5.
        the ratings ratio is fixed:
        5: 0.5
        4: 0.15
        3: 0.35
        how many images are chosen from each collection is calculated as follows:
        - in case of a list of collections, n is distributed equally by n // len(collections)
        - in case of a dict of collections, the dict values are summed up to represent 1 and the size of each collection selection
        is its normalized value times n
        """
        if not isinstance(n, int) or n <= 0:
            raise ValueError("n must be a positive integer.")
        
        # make a dict of collections with as values the relative amount to choose from this collection
        collection_ratios: dict[str, int] = {}
        if isinstance(collections, list):
            for collection in collections:
                if collection not in self._dbm.collections_images:
                    continue
                collection_ratios |= {collection: 1.0}
        elif isinstance(collections, dict):
            for collection in collections:
                if collection not in self._dbm.collections_images:
                    continue
                collection_ratios |= {collection: collections[collection]}
        # make a dict of collections with as values the absolute amount to choose from this collection
        norm = 0.0
        for collection in collection_ratios:
            norm += collection_ratios[collection]
        if norm <= 0.001:
            return
        for collection in collection_ratios:
            collection_ratios[collection] = collection_ratios[collection] / norm
        
        self._imgs = {}
        rating_distribution = {
            5: 0.6,
            4: 0.2,
            3: 0.2
        }
    
        for collection in collection_ratios:
            rating = 5
            imgs = self._query.query_by_rating(rating,rating, collections=[collection])
            print(f"[SetImg] got {len(imgs)}.")
            m = int(n * rating_distribution[rating] * collection_ratios[collection])
            imgs = Query.select_rand_num(imgs, m)
            m_r5 = len(imgs)
            self.add(imgs)
            diff = m - m_r5

            rating = 4
            imgs = self._query.query_by_rating(rating,rating, collections=[collection])
            print(f"[SetImg] got {len(imgs)}.")
            m = int(n * rating_distribution[rating] * collection_ratios[collection]) + diff
            imgs = Query.select_rand_num(imgs, m)
            m_r4 = len(imgs)
            self.add(imgs)
            diff = m - m_r4

            rating = 3
            imgs = self._query.query_by_rating(rating,rating, collections=[collection])
            print(f"[SetImg] got {len(imgs)}.")
            m = int(n * rating_distribution[rating] * collection_ratios[collection]) + diff
            imgs = Query.select_rand_num(imgs, m)
            m_r3 = len(imgs)
            self.add(imgs)
            print(f"[SetImg] selected from {collection} = 5:{m_r5} 4:{m_r4} 3:{m_r3}")

    
    def _unique(self) -> None:
        for collection in self.collections:
            self._imgs[collection] = list(set(self._imgs[collection]))
    
    def store(self) -> None:
        """
        Stores set in mongodb via dbmanager
        """
        self._unique()
        # check if name already exists in collection "sets_img"
        existing_set = self._dbm.find_documents('sets_img', {"name": self.name})
        if existing_set:
            # If it exists, update it
            print(f"Set '{self.name}' already exist, overwrite not implemented.")
            return
        self._dbm.insert_document('sets_img', self.to_dict)
