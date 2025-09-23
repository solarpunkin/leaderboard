import hashlib
import math

class CountMinSketch:
    """
    A class for the Count-Min Sketch data structure.

    Attributes:
        width (int): The width of the sketch (number of columns).
        depth (int): The depth of the sketch (number of hash functions/rows).
        sketch (list): The 2D list representing the sketch.
    """
    def __init__(self, width, depth):
        """
        Initializes the Count-Min Sketch.

        Args:
            width (int): The width of the sketch.
            depth (int): The depth of the sketch.
        """
        self.width = width
        self.depth = depth
        self.sketch = [[0] * width for _ in range(depth)]

    def _get_hashes(self, item):
        """
        Generates multiple hash values for an item.

        Args:
            item (str): The item to hash.

        Returns:
            list: A list of hash values.
        """
        hashes = []
        for i in range(self.depth):
            # Use different salts for each hash function
            salt = str(i).encode()
            h = hashlib.sha256(salt + item.encode())
            hashes.append(int(h.hexdigest(), 16) % self.width)
        return hashes

    def add(self, item, count=1):
        """
        Adds an item to the sketch.

        Args:
            item (str): The item to add.
            count (int): The count to increment by.
        """
        hashes = self._get_hashes(item)
        for i in range(self.depth):
            self.sketch[i][hashes[i]] += count

    def estimate(self, item):
        """
        Estimates the count of an item.

        Args:
            item (str): The item to estimate.

        Returns:
            int: The estimated count.
        """
        hashes = self._get_hashes(item)
        min_count = float('inf')
        for i in range(self.depth):
            min_count = min(min_count, self.sketch[i][hashes[i]])
        return min_count

    def merge(self, other_sketch):
        """
        Merges another sketch into this one.

        Args:
            other_sketch (CountMinSketch): The sketch to merge.

        Raises:
            ValueError: If sketch dimensions do not match.
        """
        if self.width != other_sketch.width or self.depth != other_sketch.depth:
            raise ValueError("Sketches must have the same dimensions to be merged.")
        
        for i in range(self.depth):
            for j in range(self.width):
                self.sketch[i][j] += other_sketch.sketch[i][j]

