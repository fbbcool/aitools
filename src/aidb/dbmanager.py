from bson import ObjectId
import pymongo
import pymongo.collection
import pymongo.database
from pymongo.errors import ConnectionFailure, OperationFailure
import pathlib
import datetime
import uuid
import mimetypes
from typing import List, Dict, Optional, Union, Any, Tuple
import yaml # Import the yaml library

# Define the DBManager class for handling metadata operations
class DBManager:
    """
    A class to manage connections and operations for MongoDB, specifically
    designed for storing and retrieving image and container metadata.
    This version reads its configuration (MongoDB connection, thumbnail settings)
    from a YAML file if specified.
    """

    def __init__(self, config_file: Optional[str] = None, host: str = 'localhost', port: int = 27017, db_name: str = 'metadata_db') -> None:
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

        # Private members for default thumbnail settings, initialized with hardcoded fallbacks
        self._default_thumbnail_dir: pathlib.Path = pathlib.Path("./default_thumbnails")
        self._default_thumbnail_size: Tuple[int, int] = (128, 128)

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
            
        except ConnectionFailure as e:
            print(f"Could not connect to MongoDB: {e}")
            self.client = None
            self.db = None
        except Exception as e:
            print(f"An unexpected error occurred during MongoDB connection: {e}")
            self.client = None
            self.db = None

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
        config_path = pathlib.Path(config_file)
        if not config_path.exists():
            print(f"Warning: Configuration file '{config_file}' not found. Using constructor/default settings.")
            return

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            if config and isinstance(config, dict):
                # Load MongoDB settings
                if "mongodb_settings" in config and isinstance(config["mongodb_settings"], dict):
                    mongo_settings = config["mongodb_settings"]
                    if "host" in mongo_settings and isinstance(mongo_settings["host"], str):
                        self._host = mongo_settings["host"]
                    if "port" in mongo_settings and isinstance(mongo_settings["port"], int):
                        self._port = mongo_settings["port"]
                    if "db_name" in mongo_settings and isinstance(mongo_settings["db_name"], str):
                        self._db_name = mongo_settings["db_name"]
                    print(f"MongoDB connection configuration loaded from '{config_file}'.")
                else:
                    print(f"Warning: 'mongodb_settings' section not found or malformed in '{config_file}'. Using constructor/default MongoDB settings.")

                # Load thumbnail settings
                if "thumbnail_settings" in config and isinstance(config["thumbnail_settings"], dict):
                    thumb_settings = config["thumbnail_settings"]
                    if "default_thumbnail_dir" in thumb_settings and isinstance(thumb_settings["default_thumbnail_dir"], str):
                        self._default_thumbnail_dir = pathlib.Path(thumb_settings["default_thumbnail_dir"])
                    if "default_thumbnail_size" in thumb_settings and isinstance(thumb_settings["default_thumbnail_size"], list) and len(thumb_settings["default_thumbnail_size"]) == 2:
                        self._default_thumbnail_size = tuple(thumb_settings["default_thumbnail_size"])
                    print(f"Thumbnail configuration loaded from '{config_file}'.")
                else:
                    print(f"Warning: 'thumbnail_settings' section not found or malformed in '{config_file}'. Using default thumbnail settings.")
            else:
                print(f"Warning: Configuration file '{config_file}' is empty or malformed. Using constructor/default settings.")

        except yaml.YAMLError as e:
            print(f"Error parsing YAML file '{config_file}': {e}. Using constructor/default settings.")
        except Exception as e:
            print(f"An unexpected error occurred while reading '{config_file}': {e}. Using constructor/default settings.")
        

    @property
    def default_thumbnail_dir(self) -> pathlib.Path:
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

    def add_container(self, container_local_path: str, recursive: bool = False) -> Optional[str]:
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
        container_path_obj = pathlib.Path(container_local_path)

        if not container_path_obj.is_dir():
            print(f"Error: Container path '{container_local_path}' does not exist or is not a directory.")
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

    def _process_image_file(self, full_image_path_obj: pathlib.Path, base_container_path_obj: pathlib.Path, image_extensions: Dict[str, str], parent_container_db_id: ObjectId) -> Optional[str]:
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
                "tags": [], # Set tags to empty list
                "dimensions": {
                    "width": 0,  # Placeholder, actual dimensions require image processing library
                    "height": 0, # Placeholder
                    "unit": "pixels"
                },
                "container_local_path": str(base_container_path_obj), # This refers to the local path of the container
                "relative_url": str(relative_path_from_container), # Relative to the container_path
                "thumbnail_url": "", # Default thumbnail URL is an empty string
                "rating": -1, # Default rating is -1
                "category": "Uncategorized", # Default category
                "file_type": image_extensions[file_extension],
                "container_db_id": parent_container_db_id # MongoDB reference to the parent container
            }
            return self.insert_document('images', image_metadata)
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

    def update_image(self, 
                     image_id: str, # This is now expected to be the string representation of MongoDB's _id
                     description: Optional[List[Dict[str, str]]] = None, 
                     creation_date: Optional[str] = None, 
                     last_modified_date: Optional[str] = None, 
                     tags: Optional[List[Dict[str, Any]]] = None, # Tags can have 'source' and 'values'
                     dimensions: Optional[Dict[str, Union[int, str]]] = None, 
                     thumbnail_url: Optional[str] = None, 
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

        return self.update_document('images', {"_id": object_id}, {"$set": update_fields})

    def close_connection(self) -> None:
        """
        Closes the MongoDB connection.
        """
        if self.client is not None:
            self.client.close()
            print("MongoDB connection closed.")
        else:
            print("No active MongoDB connection to close.")

