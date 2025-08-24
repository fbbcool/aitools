import json
from bson import ObjectId
import pymongo
import pymongo.collection
import pymongo.database
from pymongo.errors import ConnectionFailure, OperationFailure
from  pathlib import Path
import datetime
import uuid
import mimetypes
from typing import Final, Generator, List, Dict, Optional, Union, Any, Tuple
import yaml # Import the yaml library

from aidb.hfdataset import HFDatasetImg

DBM_COLLECTION_IMG_PREFIX: Final = "imgs_"

# Define the DBManager class for handling metadata operations
class DBManager:
    """
    A class to manage connections and operations for MongoDB, specifically
    designed for storing and retrieving image and container metadata.
    This version reads its configuration (MongoDB connection, thumbnail settings)
    from a YAML file if specified.
    """

    def __init__(
            self,
            config_file: Optional[str] = None,
            host: str = 'localhost',
            port: int = 27017,
            db_name: str = '',
            collection: str = "",
            ) -> None:
        """
        Initializes the MongoDB connection. Configuration can be loaded from a YAML file.

        Args:
            config_file (Optional[str]): Path to a YAML configuration file (e.g., 'dbmanager.yaml').
                                          If provided, settings from this file will override
                                          'host', 'port', 'db_name', and default thumbnail settings.
            host (str): Default MongoDB server host. Overridden by config_file if present.
            port (int): Default MongoDB server port. Overridden by config_file if present.
            db_name (str): Default database name. Overridden by config_file if present.
        """
        self.client: Optional[pymongo.MongoClient] = None
        self.db: Optional[pymongo.database.Database] = None

        # Initialize connection parameters with provided arguments (these are fallbacks)
        self._host: str = host
        self._port: int = port
        self._db_name: str = db_name
        self._collection: str = collection

        # config
        self._config = {}

        # Hf dataset
        self._hfds: dict[str,HFDatasetImg | None] = {}
        self._collection2hfd: dict[str, str] = {}

        self._root = Path("./")
        # Private members for default thumbnail settings, initialized with hardcoded fallbacks
        self._default_thumbnail_dir: Path = Path("./default_thumbnails")
        self._default_thumbnail_size: Tuple[int, int] = (128, 128)

        # Private members for default train image settings, initialized with hardcoded fallbacks
        self._default_train_image_dir: Path = Path("./default_train_images")
        self._default_train_image_size: Tuple[int, int] = (1024, 1024)

        # Load configuration from YAML file if provided. This will populate self._host, etc.
        if config_file:
            self._load_config_from_yaml(config_file)
        
        # Ensure the thumbnail directory exists based on loaded/default path
        self._default_thumbnail_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Attempt to connect to MongoDB using the (potentially overridden by YAML) settings
            self.client = pymongo.MongoClient(self._host, self._port, serverSelectionTimeoutMS=5000)
            # The ismaster command is cheap and does not require auth.
            self.client.admin.command('ismaster')
            self.db = self.client[self._db_name]
            print(f"Successfully connected to MongoDB at {self._host}:{self._port}, database: {self._db_name}")
            print(f"Using collection {self._collection}")
            
        except ConnectionFailure as e:
            print(f"Could not connect to MongoDB: {e}")
            self.client = None
            self.db = None
        except Exception as e:
            print(f"An unexpected error occurred during MongoDB connection: {e}")
            self.client = None
            self.db = None

    @property
    def hfds(self):
        for repo_id in self._hfds:
            yield self._hfds[repo_id]

    def get_hfd(self, repo_id: str) -> HFDatasetImg | None:
        """
        Tries to load a hugging face dataset by repo_id.
        returns None if creation fails
        """
        if repo_id in self._hfds:
            return self._hfds[repo_id]
        try:
            hfd = HFDatasetImg(repo_id, force_meta_dl=True)
            self._hfds[repo_id] = hfd
            return hfd
        except Exception as e:
            print(f"Failed connecting to HF dataset: {repo_id}\n{e}")
            self._hfds[repo_id] = None
            return None
    
    def get_collection_hfd(self, collection: str) -> str | None:
        if collection is None:
            return None
        if not collection:
            return None
        return self._collection2hfd.get(collection, None)
    
    def set_collection(self, collection_name: str, create: bool = False) -> None:
        """
        Sets the currently used collection.

        The collection is only changed if the collection exists, otherwise an Exception is raised.
        """
        if self.db is None:
            print("Database not connected. Cannot set collection.")
            return

        if collection_name not in self.db.list_collection_names():
            if create:
                self.create_collection(collection_name)
            else:
                raise ValueError(f"Collection '{collection_name}' does not exist in the database.")
        
        self._collection = collection_name
        print(f"Collection set to: {self._collection}")

    def create_collection(self, collection_name: str) -> None:
        """
        Creates a new collection in the current database.
        """
        if self.db is None:
            print("Database not connected. Cannot create collection.")
            return

        self.db.create_collection(collection_name)
        print(f"Collection '{collection_name}' created.")


    @property
    def collections_images(self) -> list[str]:
        """
        Returns all collection names of the current DB.
        """
        if self.db is None:
            print("Database not connected. Cannot retrieve collection names.")
            return []
        
        # List all collection names in the current database
        collections = self.db.list_collection_names()
        collections_filtered = [collection for collection in collections if collection.startswith(DBM_COLLECTION_IMG_PREFIX)]
        return collections_filtered
    
    def collection_rename(self, name_to: str, name_from: str):
        """
        Renames a collection in the DB.
        """
        if self.db is None:
            print("Database not connected. Cannot rename collection.")
            return

        try:
            self.db[name_from].rename(name_to)
            print(f"Collection '{name_from}' renamed to '{name_to}'.")
            # If the current collection name matches the old name, update it
            if self._collection == name_from:
                self._collection = name_to
        except OperationFailure as e:
            print(f"Failed to rename collection '{name_from}' to '{name_to}': {e}")
        except Exception as e:
            print(f"An unexpected error occurred during collection rename: {e}")

    def _get_collection(self, collection_name: str) -> Optional[pymongo.collection.Collection]:
        """
        Helper method to get a specific collection from the database.

        Args:
            collection_name (str): The name of the collection to retrieve.

        Returns:
            pymongo.collection.Collection or None: The MongoDB collection object, or None if DB is not connected.
        """
        if self.db is not None:
            return self.db[collection_name]
        else:
            print("Database not connected. Cannot access collection.")
            return None

    def _load_config_from_yaml(self, config_file: str) -> None:
        """
        Loads configuration settings from a YAML file.
        Updates private members for MongoDB connection and thumbnail settings.
        """
        config_path = Path(config_file)
        if not config_path.exists():
            print(f"Warning: Configuration file '{config_file}' not found. Using constructor/default settings.")
            return

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            if config and isinstance(config, dict):
                self._config = config
                # Load MongoDB settings
                if "mongodb_settings" in config and isinstance(config["mongodb_settings"], dict):
                    mongo_settings = config["mongodb_settings"]
                    if "host" in mongo_settings and isinstance(mongo_settings["host"], str):
                        self._host = mongo_settings["host"]
                    if "port" in mongo_settings and isinstance(mongo_settings["port"], int):
                        self._port = mongo_settings["port"]
                    if "db_name" in mongo_settings and isinstance(mongo_settings["db_name"], str):
                        self._db_name = mongo_settings["db_name"]
                    if "collection" in mongo_settings and isinstance(mongo_settings["collection"], str):
                        self._collection = mongo_settings["collection"]
                    print(f"MongoDB connection configuration loaded from '{config_file}'.")
                else:
                    print(f"Warning: 'mongodb_settings' section not found or malformed in '{config_file}'. Using constructor/default MongoDB settings.")

                # Load directory settings
                if "directory_settings" in config and isinstance(config["directory_settings"], dict):
                    directory_settings = config["directory_settings"]
                    if "root_dir" in directory_settings and isinstance(directory_settings["root_dir"], str):
                        self._root = Path(directory_settings["root_dir"])
                
                # Load thumbnail settings
                if "thumbnail_settings" in config and isinstance(config["thumbnail_settings"], dict):
                    thumb_settings = config["thumbnail_settings"]
                    if "default_thumbnail_dir" in thumb_settings and isinstance(thumb_settings["default_thumbnail_dir"], str):
                        self._default_thumbnail_dir = self._root / thumb_settings["default_thumbnail_dir"]
                    if "default_thumbnail_size" in thumb_settings and isinstance(thumb_settings["default_thumbnail_size"], list) and len(thumb_settings["default_thumbnail_size"]) == 2:
                        self._default_thumbnail_size = tuple(thumb_settings["default_thumbnail_size"])
                    print(f"Thumbnail configuration loaded from '{config_file}'.")
                else:
                    print(f"Warning: 'thumbnail_settings' section not found or malformed in '{config_file}'. Using default thumbnail settings.")

                # Load train images settings
                if "train_image_settings" in config and isinstance(config["train_image_settings"], dict):
                    train_img_settings = config["train_image_settings"]
                    if "default_train_image_dir" in train_img_settings and isinstance(train_img_settings["default_train_image_dir"], str):
                        self._default_train_image_dir = self._root / train_img_settings["default_train_image_dir"]
                    if "default_train_image_size" in train_img_settings and isinstance(train_img_settings["default_train_image_size"], list) and len(train_img_settings["default_train_image_size"]) == 2:
                        self._default_train_image_size = tuple(train_img_settings["default_train_image_size"])
                    print(f"Train image configuration loaded from '{config_file}'.")
                else:
                    print(f"Warning: 'train_image_settings' section not found or malformed in '{config_file}'. Using default train image settings.")
                
                # Load HF dataset
                if "hf_settings" in config and isinstance(config["hf_settings"], dict):
                    hf_settings = config["hf_settings"]
                    if "preload" in hf_settings and isinstance(hf_settings["preload"], list):
                        for repo_id in hf_settings["preload"]:
                            _ = self.get_hfd(repo_id)
                    if "collection2hfd" in hf_settings and isinstance(hf_settings["collection2hfd"], list):
                        collection2hfd = {}
                        for mapping in hf_settings["collection2hfd"]:
                            collection2hfd |= mapping
                        self._collection2hfd = collection2hfd
                else:
                    print(f"Warning: 'hf_dataset_settings' section not found or malformed in '{config_file}'. Using default HF dataset settings.")
                    
                    

            else:
                print(f"Warning: Configuration file '{config_file}' is empty or malformed. Using constructor/default settings.")

        except yaml.YAMLError as e:
            print(f"Error parsing YAML file '{config_file}': {e}. Using constructor/default settings.")
        except Exception as e:
            print(f"An unexpected error occurred while reading '{config_file}': {e}. Using constructor/default settings.")
        

    @property
    def image_ids(self):
        """Returns a generator of Images id's for all images in the db"""
        if self.db is None:
            print("Database not connected. Cannot retrieve image IDs.")
            return

        image_docs = self.find_documents(self._collection, query={}, projection={'_id': 1}) # Only fetch _id
        for doc in image_docs:
            yield str(doc['_id'])


    @property
    def images(self):
        """Returns a generator of Images instances for all images in the db"""
        if self.db is None:
            print("Database not connected. Cannot retrieve images.")
            return

        from aidb.image import Image # Import here to avoid circular dependency

        image_docs = self.find_documents(self._collection)
        for doc in image_docs:
            # Ensure _id is converted to string for Image object initialization
            yield Image(self, str(doc['_id']), doc=doc)

    @property
    def container_names(self) -> Generator:
        """Returns a generator of for all container names in the db"""
        if self.db is None:
            print("Database not connected.")
            return

        docs = self.find_documents('containers')
        for doc in docs:
            yield doc["name"]
    
    @property
    def sets_img_names(self) -> list[str]:
        sets = self.find_documents('sets_img')
        return [s["name"] for s in sets]

    @property
    def default_thumbnail_dir(self) -> Path:
        """
        Returns the default directory for storing thumbnails.
        """
        return self._default_thumbnail_dir


    @property
    def default_thumbnail_size(self) -> Tuple[int, int]:
        """
        Returns the default size (width, height) for generated thumbnails.
        """
        return self._default_thumbnail_size

    # properties for train images defaults
    @property
    def default_train_image_dir(self) -> Path:
        """
        Returns the default directory for storing train images.
        """
        return self._default_train_image_dir

    @property
    def default_train_image_size(self) -> Tuple[int, int]:
        """
        Returns the default size (width, height) for generated train images.
        """
        return self._default_train_image_size
        

    def insert_document(self, collection_name: str, document: Dict[str, Any]) -> Optional[str]:
        """
        Inserts a single document into the specified collection.

        Args:
            collection_name (str): The name of the collection.
            document (dict): The document to insert.

        Returns:
            str or None: The string representation of the MongoDB '_id' of the inserted document, or None on failure.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                result = collection.insert_one(document)
                # MongoDB automatically generates '_id'
                print(f"Document inserted into '{collection_name}' with MongoDB _id: {result.inserted_id}")
                return str(result.inserted_id)
            except OperationFailure as e:
                print(f"Failed to insert document into '{collection_name}': {e}")
            except Exception as e:
                print(f"An unexpected error occurred during insertion into '{collection_name}': {e}")
        return None

    def find_documents(self, collection_name: str, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Finds documents in the specified collection based on a query.
        Note: If querying by '_id', ensure the value is an ObjectId.

        Args:
            collection_name (str): The name of the collection.
            query (dict, optional): The query to filter documents. If None, all documents are returned.

        Returns:
            list: A list of found documents.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                if query is None:
                    query = {}
                return list(collection.find(query))
            except OperationFailure as e:
                print(f"Failed to find documents in '{collection_name}': {e}")
            except Exception as e:
                print(f"An unexpected error occurred during finding documents in '{collection_name}': {e}")
        return []

    def update_document(self, collection_name: str, query: Dict[str, Any], new_values: Dict[str, Any]) -> Optional[int]:
        """
        Updates documents in the specified collection.
        Note: If querying by '_id', ensure the value in the query is an ObjectId.

        Args:
            collection_name (str): The name of the collection.
            query (dict): The query to select documents to update.
            new_values (dict): The new values to set. Use MongoDB update operators (e.g., {"$set": {...}}).

        Returns:
            int or None: The number of modified documents, or None on failure.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                result = collection.update_many(query, new_values)
                print(f"Modified {result.modified_count} document(s) in '{collection_name}'.")
                return result.modified_count
            except OperationFailure as e:
                print(f"Failed to update documents in '{collection_name}': {e}")
            except Exception as e:
                print(f"An unexpected error occurred during updating documents in '{collection_name}': {e}")
        return None

    def delete_document(self, collection_name: str, query: Dict[str, Any]) -> Optional[int]:
        """
        Deletes documents from the specified collection.
        Note: If querying by '_id', ensure the value in the query is an ObjectId.

        Args:
            collection_name (str): The name of the collection.
            query (dict): The query to select documents to delete.

        Returns:
            int or None: The number of deleted documents, or None on failure.
        """
        collection = self._get_collection(collection_name)
        if collection is not None:
            try:
                result = collection.delete_many(query)
                print(f"Deleted {result.deleted_count} document(s) from '{collection_name}'.")
                return result.deleted_count
            except OperationFailure as e:
                print(f"Failed to delete documents from '{collection_name}': {e}")
            except Exception as e:
                print(f"An unexpected error occurred during deleting documents from '{collection_name}': {e}")
        return None

    def add_container(self, container_local_path: str | Path, collection: str | None = None, recursive: bool = False) -> Optional[str]:
        """
        Creates a new container based on a local path and adds all images
        contained in that path, optionally recursively.

        Args:
            container_local_path (str): The local file system path to the container directory.
            recursive (bool): If True, recursively search for images in subdirectories.
                              Defaults to False.

        Returns:
            str or None: The string representation of the MongoDB '_id' of the newly created container, or None on failure.
        """
        if collection is not None:
            self.set_collection(collection, create = True)

        if isinstance(container_local_path, str):
            container_path_obj = Path(container_local_path)
        elif isinstance(container_local_path, Path):
            container_path_obj = container_local_path
        else:
            raise TypeError(f"{container_local_path} has wrong type!")

        if not container_path_obj.is_dir():
            print(f"Error: Container path '{container_local_path}' does not exist or is not a directory.")
            return None

        if not container_path_obj.exists():
            print(f"Error: Container path '{container_local_path}' exists, force option not implemented!")
            return None

        # Generate container metadata
        container_name = container_path_obj.name
        
        # Get creation and modification dates for the container directory
        try:
            container_creation_timestamp = container_path_obj.stat().st_ctime
            container_modified_timestamp = container_path_obj.stat().st_mtime
            container_creation_date = datetime.datetime.fromtimestamp(container_creation_timestamp).isoformat() + "Z"
            container_last_modified_date = datetime.datetime.fromtimestamp(container_modified_timestamp).isoformat() + "Z"
        except OSError as e:
            print(f"Error getting container directory timestamps: {e}")
            container_creation_date = datetime.datetime.now().isoformat() + "Z"
            container_last_modified_date = datetime.datetime.now().isoformat() + "Z"

        container_metadata = {
            "name": container_name,
            "container_path": str(container_path_obj), # Storing local path for reference
            "description": "", # Set description to empty string
            "creation_date": container_creation_date,
            "last_modified_date": container_last_modified_date,
            "tags": {}, # Set tags to empty dict
            "image_ids": [] # Initialize an empty list to store ObjectIds of images
        }

        inserted_container_id = self.insert_document('containers', container_metadata)
        if inserted_container_id is None:
            print(f"Failed to insert container metadata for '{container_local_path}'.")
            return None
        
        # Convert the string ID back to ObjectId for internal use
        inserted_container_object_id = ObjectId(inserted_container_id)

        print(f"Container '{container_name}' added with ID: {inserted_container_id}")

        # Supported image extensions and their MIME types
        image_extensions = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.gif': 'image/gif', '.bmp': 'image/bmp', '.tiff': 'image/tiff',
            '.webp': 'image/webp'
        }

        # List to hold ObjectIds of images added to this container
        added_image_object_ids: List[ObjectId] = []

        # Iterate through files in the container path
        if recursive:
            # Use rglob for recursive search
            for file_path_obj in container_path_obj.rglob('*'):
                if file_path_obj.is_file():
                    image_db_id = self._process_image_file(file_path_obj, container_path_obj, image_extensions, inserted_container_object_id)
                    if image_db_id:
                        added_image_object_ids.append(ObjectId(image_db_id))
        else:
            # Use iterdir for non-recursive search
            for file_path_obj in container_path_obj.iterdir():
                if file_path_obj.is_file():
                    image_db_id = self._process_image_file(file_path_obj, container_path_obj, image_extensions, inserted_container_object_id)
                    if image_db_id:
                        added_image_object_ids.append(ObjectId(image_db_id))
        
        # Update the container document with the list of image ObjectIds
        if added_image_object_ids:
            self.update_document(
                'containers',
                {"_id": inserted_container_object_id},
                {"$set": {"image_ids": added_image_object_ids}}
            )
            print(f"Container '{container_name}' ({inserted_container_id}) updated with {len(added_image_object_ids)} image references.")
        else:
            print(f"No images found or added to container '{container_name}' ({inserted_container_id}).")

        return inserted_container_id

    def _process_image_file(self, full_image_path_obj: Path, base_container_path_obj: Path, image_extensions: Dict[str, str], parent_container_db_id: ObjectId) -> Optional[str]:
        """
        Helper method to process a single image file and insert its metadata.
        
        Args:
            full_image_path_obj (pathlib.Path): The full Path object of the image file.
            base_container_path_obj (pathlib.Path): The base Path object of the container.
            image_extensions (dict): Dictionary of supported image extensions and MIME types.
            parent_container_db_id (ObjectId): The MongoDB '_id' of the parent container document.

        Returns:
            Optional[str]: The string representation of the MongoDB '_id' of the inserted image, or None on failure.
        """
        file_extension = full_image_path_obj.suffix.lower()
        if file_extension in image_extensions:
            
            # Calculate relative path from the base container path
            relative_path_from_container = full_image_path_obj.relative_to(base_container_path_obj)

            # Get file timestamps
            try:
                file_creation_timestamp = full_image_path_obj.stat().st_ctime
                file_modified_timestamp = full_image_path_obj.stat().st_mtime
                file_creation_date = datetime.datetime.fromtimestamp(file_creation_timestamp).isoformat() + "Z"
                file_last_modified_date = datetime.datetime.fromtimestamp(file_modified_timestamp).isoformat() + "Z"
            except OSError as e:
                print(f"Error getting file timestamps for '{full_image_path_obj}': {e}")
                file_creation_date = datetime.datetime.now().isoformat() + "Z"
                file_last_modified_date = datetime.datetime.now().isoformat() + "Z"

            # Simulate image metadata (as we cannot read actual image data here)
            image_metadata = {
                "description": [], # Set description to empty list
                "creation_date": file_creation_date,
                "last_modified_date": file_last_modified_date,
                "tags": {}, # Set tags to empty dict
                "dimensions": {
                    "width": 0,  # Placeholder, actual dimensions require image processing library
                    "height": 0, # Placeholder
                    "unit": "pixels"
                },
                "container_local_path": str(base_container_path_obj), # This refers to the local path of the container
                "relative_url": str(relative_path_from_container), # Relative to the container_path
                "thumbnail_url": "", # Default thumbnail URL is an empty string
                "train_image_url": "", # Default thumbnail URL is an empty string
                "rating": -1, # Default rating is -1
                "category": "Uncategorized", # Default category
                "file_type": image_extensions[file_extension],
                "container_db_id": parent_container_db_id, # MongoDB reference to the parent container
                "statistics": {},
                "train_image_url": ""
            }
            return self.insert_document(self._collection, image_metadata)
        else:
            print(f"Skipping non-image file: {full_image_path_obj.name}")
            return None


    def update_container(self, 
                         container_id: str, # This is now expected to be the string representation of MongoDB's _id
                         name: Optional[str] = None, 
                         description: Optional[str] = None, 
                         creation_date: Optional[str] = None, 
                         last_modified_date: Optional[str] = None, 
                         tags: Optional[dict] = None,
                         image_ids: Optional[List[str]] = None # Allow updating image_ids directly
                         ) -> Optional[int]:
        """
        Updates specific fields of an existing container document.

        Args:
            container_id (str): The string representation of the MongoDB '_id' of the container to update.
            name (Optional[str]): New name for the container.
            description (Optional[str]): New description for the container.
            creation_date (Optional[str]): New creation date (ISO format) for the container.
            last_modified_date (Optional[str]): New last modified date (ISO format) for the container.
            tags (Optional[List[str]]): New list of tags for the container.
            image_ids (Optional[List[str]]): New list of string representations of MongoDB '_id's for images.

        Returns:
            Optional[int]: The number of modified documents, or None on failure.
        """
        update_fields: Dict[str, Any] = {}
        if name is not None:
            update_fields["name"] = name
        if description is not None:
            update_fields["description"] = description
        if creation_date is not None:
            update_fields["creation_date"] = creation_date
        if last_modified_date is not None:
            update_fields["last_modified_date"] = last_modified_date
        if tags is not None:
            update_fields["tags"] = tags
        if image_ids is not None:
            # Convert string IDs to ObjectId for storage
            try:
                update_fields["image_ids"] = [ObjectId(img_id) for img_id in image_ids]
            except Exception:
                print(f"Invalid image_ids format: one or more IDs are not valid ObjectId strings.")
                return None
        
        if not update_fields:
            print("No fields provided for container update.")
            return 0

        try:
            object_id = ObjectId(container_id)
        except Exception:
            print(f"Invalid container_id format: {container_id}")
            return None
        
        return self.update_document('containers', {"_id": object_id}, {"$set": update_fields})
    
    def name_container(self, container_id: str | ObjectId) -> str | None:
        """
        Returns the name of a container.
        """
        if isinstance(container_id, str):
            container_id = ObjectId(container_id)
        container = self.find_documents('containers', {"_id": container_id})
        if container:
            return container[0]["name"]
        else:
            return None

    def update_image(self, 
                     image_id: str, # This is now expected to be the string representation of MongoDB's _id
                     description: Optional[List[Dict[str, str]]] = None, 
                     creation_date: Optional[str] = None, 
                     last_modified_date: Optional[str] = None, 
                     tags: Optional[List[Dict[str, Any]]] = None, # Tags can have 'source' and 'values'
                     dimensions: Optional[Dict[str, Union[int, str]]] = None, 
                     thumbnail_url: Optional[str] = None, 
                     train_image_url: Optional[str] = None, 
                     rating: Optional[int] = None, 
                     category: Optional[str] = None,
                     container_db_id: Optional[str] = None # Allow updating container_db_id
                     ) -> Optional[int]:
        """
        Updates specific fields of an existing image document.

        Args:
            image_id (str): The string representation of the MongoDB '_id' of the image to update.
            description (Optional[List[Dict[str, str]]]): New list of description objects for the image.
            creation_date (Optional[str]): New creation date (ISO format) for the image.
            last_modified_date (Optional[str]): New last modified date (ISO format) for the image.
            tags (Optional[List[Dict[str, Any]]]): New list of tag objects for the image.
            dimensions (Optional[Dict[str, Union[int, str]]]): New dimensions object (width, height, unit).
            thumbnail_url (Optional[str]): New URL for the thumbnail.
            train_image_url (Optional[str]): New URL for the training image.
            rating (Optional[int]): New rating for the image (e.g., 1-5).
            category (Optional[str]): New category for the image.
            container_db_id (Optional[str]): New string representation of MongoDB '_id' for the parent container.

        Returns:
            Optional[int]: The number of modified documents, or None on failure.
        """
        update_fields: Dict[str, Any] = {}
        if description is not None:
            update_fields["description"] = description
        if creation_date is not None:
            update_fields["creation_date"] = creation_date
        if last_modified_date is not None:
            update_fields["last_modified_date"] = last_modified_date
        if tags is not None:
            update_fields["tags"] = tags
        if dimensions is not None:
            update_fields["dimensions"] = dimensions
        if thumbnail_url is not None:
            update_fields["thumbnail_url"] = thumbnail_url
        if train_image_url is not None:
            update_fields["train_image_url"] = train_image_url
        if rating is not None:
            update_fields["rating"] = rating
        if category is not None:
            update_fields["category"] = category
        if container_db_id is not None:
            try:
                update_fields["container_db_id"] = ObjectId(container_db_id)
            except Exception:
                print(f"Invalid container_db_id format: {container_db_id}")
                return None

        if not update_fields:
            print("No fields provided for image update.")
            return 0
        
        try:
            object_id = ObjectId(image_id)
        except Exception:
            print(f"Invalid image_id format: {image_id}")
            return None

        return self.update_document(self._collection, {"_id": object_id}, {"$set": update_fields})
    
    def img_add_field(self, img_id: str, fieldname: str, value: Any = {}, force=False):
        """Adds a new data field to the image document. If the field already exists, the force option is taken into account."""
        collection = self._get_collection(self._collection)
        if collection is not None:
            try:
                # Check if the field already exists
                existing_doc = collection.find_one({"_id": ObjectId(img_id)}, {fieldname: 1})
                if existing_doc and fieldname in existing_doc:
                    if not force:
                        print(f"Field '{fieldname}' already exists for image {img_id}. Use force=True to overwrite.")
                        return 0
                    else:
                        print(f"Field '{fieldname}' already exists for image {img_id}. Overwriting as force=True.")
                
                # Add or overwrite the field
                result = collection.update_one(
                    {"_id": ObjectId(img_id)},
                    {"$set": {fieldname: value}}
                )
                if result.modified_count > 0:
                    print(f"Field '{fieldname}' added/updated for image {img_id}.")
                    return result.modified_count
                else:
                    print(f"Image {img_id} not found or field '{fieldname}' not modified.")
                    return 0
            except OperationFailure as e:
                print(f"Failed to add/update field '{fieldname}' for image {img_id}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while adding/updating field '{fieldname}' for image {img_id}: {e}")
        return None

    def close_connection(self) -> None:
        """
        Closes the MongoDB connection.
        """
        if self.client is not None:
            self.client.close()
            print("MongoDB connection closed.")
        else:
            print("No active MongoDB connection to close.")
    
    def export_db(self):
        """exports the current db to a file named like the current db name. if the file already exists, it will be overwritten."""
        if self.db is None:
            print("Database not connected. Cannot export.")
            return

        db_name = self.db.name
        export_file_name = f"{db_name}_export.json"
        
        export_data = {}
        for collection_name in self.db.list_collection_names():
            collection = self.db[collection_name]
            export_data[collection_name] = []
            for document in collection.find({}):
                # Convert ObjectId to string for JSON serialization
                document['_id'] = str(document['_id'])
                # Convert any other ObjectIds in the document to string
                for key, value in document.items():
                    if isinstance(value, ObjectId):
                        document[key] = str(value)
                    elif isinstance(value, list):
                        document[key] = [str(item) if isinstance(item, ObjectId) else item for item in value]
                export_data[collection_name].append(document)

        try:
            with open(export_file_name, 'w') as f:
                json.dump(export_data, f, indent=4)
            print(f"Database '{db_name}' exported successfully to '{export_file_name}'.")
        except IOError as e:
            print(f"Error writing export file '{export_file_name}': {e}")
        except Exception as e:
            print(f"An unexpected error occurred during database export: {e}")

    def import_db(self, import_file_name: str, db_name: str) -> None:
        """imports a database from a file to a new database. if the database already exists, the export is canceled."""
        if self.client is None:
            print("MongoDB client not initialized. Cannot import.")
            return

        # Check if the target database already exists
        if db_name in self.client.list_database_names():
            print(f"Error: Database '{db_name}' already exists. Import canceled to prevent accidental overwrite.")
            print("Please drop the existing database or choose a different name for import.")
            return

        try:
            with open(import_file_name, 'r') as f:
                import_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: Import file '{import_file_name}' not found.")
            return
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from '{import_file_name}': {e}")
            return
        except Exception as e:
            print(f"An unexpected error occurred while reading import file '{import_file_name}': {e}")
            return

        # Connect to the new database
        new_db = self.client[db_name]
        print(f"Attempting to import data into new database '{db_name}'...")

        for collection_name, documents in import_data.items():
            collection = new_db[collection_name]
            docs_to_insert = []
            for doc in documents:
                # Convert string _id back to ObjectId
                if '_id' in doc:
                    doc['_id'] = ObjectId(doc['_id'])
                # Convert any other ObjectIds back
                for key, value in doc.items():
                    if isinstance(value, str):
                        try:
                            # Check if it's a valid ObjectId string
                            if len(value) == 24 and all(c in '0123456789abcdefABCDEF' for c in value):
                                doc[key] = ObjectId(value)
                        except Exception:
                            pass # Not an ObjectId string
                    elif isinstance(value, list):
                        new_list = []
                        for item in value:
                            if isinstance(item, str):
                                try:
                                    if len(item) == 24 and all(c in '0123456789abcdefABCDEF' for c in item):
                                        new_list.append(ObjectId(item))
                                    else:
                                        new_list.append(item)
                                except Exception:
                                    new_list.append(item)
                            else:
                                new_list.append(item)
                        doc[key] = new_list
                docs_to_insert.append(doc)
            
            if docs_to_insert:
                try:
                    collection.insert_many(docs_to_insert)
                    print(f"Imported {len(docs_to_insert)} documents into collection '{collection_name}'.")
                except OperationFailure as e:
                    print(f"Error inserting documents into '{collection_name}': {e}")
            else:
                print(f"No documents to insert into collection '{collection_name}'.")
        
        print(f"Database '{db_name}' imported successfully from '{import_file_name}'.")
        # Update the current DBManager's connection to the newly imported database
        self.db = new_db
        self._db_name = db_name