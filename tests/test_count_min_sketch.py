import unittest
import sys
import os

# Add src directory to path to import the modules to be tested
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from common.count_min_sketch import CountMinSketch

class TestCountMinSketch(unittest.TestCase):

    def test_add_and_estimate(self):
        """Test adding items and estimating their counts."""
        cms = CountMinSketch(width=1000, depth=5)
        
        cms.add("apple")
        cms.add("apple")
        cms.add("banana")
        
        # The estimate should be at least the number of times added
        self.assertGreaterEqual(cms.estimate("apple"), 2)
        self.assertGreaterEqual(cms.estimate("banana"), 1)
        self.assertGreaterEqual(cms.estimate("orange"), 0)

    def test_merge(self):
        """Test merging two Count-Min Sketch instances."""
        cms1 = CountMinSketch(width=1000, depth=5)
        cms1.add("apple", count=5)

        cms2 = CountMinSketch(width=1000, depth=5)
        cms2.add("apple", count=3)
        cms2.add("banana", count=2)

        cms1.merge(cms2)

        self.assertGreaterEqual(cms1.estimate("apple"), 8)
        self.assertGreaterEqual(cms1.estimate("banana"), 2)

    def test_merge_dimension_mismatch(self):
        """Test that merging sketches with different dimensions raises an error."""
        cms1 = CountMinSketch(width=1000, depth=5)
        cms2 = CountMinSketch(width=500, depth=5) # Different width

        with self.assertRaises(ValueError):
            cms1.merge(cms2)

if __name__ == '__main__':
    unittest.main()
