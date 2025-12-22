# Smart Auth Rotation Design & Implementation

## 1. Overview
The "Smart Efficiency" auth rotation logic optimizes profile selection to maximize resource availability. It moves away from a simple "lowest usage" sort to a priority system that prefers "partially exhausted" profiles for tasks they can still perform.

## 2. Core Logic

### Hierarchy of Selection
When selecting a profile for a target model (e.g., `gemini-3-pro`), the system prioritizes candidates in this order:

1.  **Efficiency Score (Primary)**:
    -   **Goal**: Recycle "damaged goods".
    -   **Calculation**: Count of *active* cooldowns for *other* models.
    -   **Logic**: If Profile A is blocked on `gemini-2.5` (quota exceeded) but valid for `gemini-3`, it gets a HIGHER score than a completely fresh Profile B. This preserves Profile B for future requests that might strictly need `gemini-2.5`.

2.  **Usage Count (Secondary)**:
    -   **Goal**: Wear leveling.
    -   **Logic**: Among profiles with the same Efficiency Score, choose the one with the lowest total token usage.

3.  **Random Factor (Tertiary)**:
    -   **Goal**: Avoid deterministic hotspots.
    -   **Logic**: Tie-breaker to prevent race conditions or "hot profile" issues in concurrent environments.

### Filtering Rules (Strict)
Before sorting, profiles are strictly filtered out if:
-   They are in **Global Cooldown** (Rate Limited).
-   They are in **Target Model Cooldown** (Quota Exceeded for the specific requested model).

## 3. Implementation Details

### Function: `_calculate_smart_priority`
Located in `browser_utils/auth_rotation.py`.

```python
def _calculate_smart_priority(profile_path, target_model_id, cooldown_dict):
    # ...
    return (-efficiency_score, usage_count, random_factor)
```
*Note: Python tuples are sorted element-by-element. We use negative efficiency score to achieve descending sort order (higher efficiency first).*

### Data Structures
-   **Cooldowns**: `config/cooldown_status.json` stores model-specific timestamps.
    -   `{"profile.json": {"gemini-2.5-pro": <timestamp>, "global": <timestamp>}}`
-   **Usage**: `config/profile_usage.json` stores total token counts.

## 4. Verification
A standalone test script `tests/test_smart_rotation_logic.py` verifies the behavior:
1.  **Efficiency Test**: Confirms selection of a partially exhausted profile over a fresh one.
2.  **Safety Test**: Confirms exclusion of profiles exhausted for the *requested* model.
3.  **Wear Leveling Test**: Confirms usage-based balancing when efficiency scores are equal.