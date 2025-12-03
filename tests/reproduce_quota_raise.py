import sys
import os

# Add workspace root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.global_state import GlobalState
from models.exceptions import QuotaExceededError
from config.settings import QUOTA_HARD_LIMIT

def test_quota_hard_limit_raises():
    print(f"Testing Quota Hard Limit Raise...")
    # Reset state
    GlobalState.reset_quota_status()
    
    # We need to ensure we hit the limit.
    # The hard limit is imported from settings.
    # We can just increment by a huge amount.
    
    huge_amount = QUOTA_HARD_LIMIT + 10000
    print(f"Incrementing token count by {huge_amount} (Limit: {QUOTA_HARD_LIMIT})")
    
    try:
        GlobalState.increment_token_count(huge_amount, model_id="test_model_reproduce")
        print("RESULT: Did not raise QuotaExceededError (Current Behavior)")
    except QuotaExceededError:
        print("RESULT: Caught QuotaExceededError successfully (Desired Behavior)")
    except Exception as e:
        print(f"RESULT: Caught unexpected exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_quota_hard_limit_raises()