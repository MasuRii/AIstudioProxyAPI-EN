#!/usr/bin/env python3
"""
Script to clean up redundant 'default' entries in cooldown_status.json
Removes 'default' entries when specific model entries exist for the same profile
"""

import json
import os


def cleanup_cooldown_file():
    cooldown_file = "config/cooldown_status.json"
    
    if not os.path.exists(cooldown_file):
        print(f"[ERROR] Cooldown file not found: {cooldown_file}")
        return
    
    with open(cooldown_file, 'r') as f:
        data = json.load(f)
    
    cleaned_profiles = 0
    removed_defaults = 0
    
    for profile_path, models in data.items():
        if isinstance(models, dict):
            original_models = list(models.keys())
            has_specific_models = any(model_id != "default" for model_id in original_models)
            
            if has_specific_models and "default" in models:
                profile_name = os.path.basename(profile_path)
                print(f"[CLEANUP] Cleaning up 'default' entry for {profile_name}")
                del models["default"]
                cleaned_profiles += 1
                removed_defaults += 1
                print(f"  [OK] Removed 'default', keeping: {[m for m in original_models if m != 'default']}")
            elif "default" in models and len(models) == 1:
                # Keep 'default' if it's the only entry (no specific models)
                print(f"[KEEP] Keeping 'default' for {os.path.basename(profile_path)} (only entry)")
    
    # Write cleaned data back to file
    with open(cooldown_file, 'w') as f:
        json.dump(data, f, indent=4)
    
    print(f"\n[COMPLETE] Cleanup complete!")
    print(f"  Cleaned profiles: {cleaned_profiles}")
    print(f"  Removed 'default' entries: {removed_defaults}")
    
    # Show summary
    print(f"\n[SUMMARY] Final Cooldown Status Summary:")
    specific_only = 0
    default_only = 0
    mixed = 0
    
    for profile_path, models in data.items():
        profile_name = os.path.basename(profile_path)
        if isinstance(models, dict):
            model_keys = list(models.keys())
            if "default" in model_keys and len(model_keys) == 1:
                default_only += 1
                print(f"  [DEFAULT_ONLY] {profile_name}: only 'default'")
            elif "default" in model_keys:
                mixed += 1
                print(f"  [MIXED] {profile_name}: {model_keys} (has 'default')")
            else:
                specific_only += 1
                print(f"  [SPECIFIC_ONLY] {profile_name}: {model_keys}")
    
    print(f"\n[STATS] Summary:")
    print(f"  Specific models only: {specific_only}")
    print(f"  Default only: {default_only}")
    print(f"  Mixed (has default): {mixed}")
    print(f"  Clean profiles: {specific_only}/{len(data)} ({specific_only/len(data)*100:.1f}%)")

if __name__ == "__main__":
    cleanup_cooldown_file()