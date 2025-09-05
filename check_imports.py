"""Check imports and module structure."""
import sys
import os
import importlib
import importlib.util
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

def check_import(module_name):
    """Check if a module can be imported."""
    print(f"\n{'='*80}")
    print(f"Checking import of: {module_name}")
    print(f"Working directory: {os.getcwd()}")
    
    try:
        # Find the module spec
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            print(f"❌ Could not find module: {module_name}")
            return False
            
        print(f"✅ Found module spec: {spec.origin}")
        
        # Import the module
        module = importlib.import_module(module_name)
        print(f"✅ Successfully imported module: {module_name}")
        print(f"Module file: {getattr(module, '__file__', 'unknown')}")
        
        # List available attributes
        print("\nAvailable attributes (non-private):")
        attrs = [attr for attr in dir(module) if not attr.startswith('_')]
        for attr in attrs[:20]:  # Show first 20 attributes to avoid too much output
            try:
                obj = getattr(module, attr)
                print(f"  - {attr}: {type(obj).__name__}")
            except Exception as e:
                print(f"  - {attr}: Error accessing - {str(e)}")
        if len(attrs) > 20:
            print(f"  ... and {len(attrs) - 20} more attributes")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print("\nTraceback:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Check the kvopt package
    check_import("kvopt")
    
    # Check the plugins
    check_import("kvopt.plugins")
    check_import("kvopt.plugins.lmcache_plugin")
    check_import("kvopt.plugins.kivi_plugin")
