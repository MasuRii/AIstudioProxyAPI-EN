# Static Assets - Modular Structure

This directory contains the refactored, modular version of the WebUI assets.

## What's Been Created

### JavaScript Modules (`js/`)

✅ **constants.js** - API URLs, localStorage keys, default values
✅ **state.js** - Global application state (models, chat history, settings)
✅ **dom.js** - DOM element references and initialization
✅ **helpers.js** - Utility functions (debounce, localStorage, formatting)

### CSS Modules (`css/`)

✅ **variables.css** - CSS custom properties for theming
✅ **base.css** - Reset, typography, global styles

## Directory Structure

```
static/
├── README.md (this file)
├── QUICKSTART.md (how to use the modules)
├── js/
│   ├── constants.js
│   ├── state.js
│   ├── dom.js
│   ├── helpers.js
│   ├── models/      (create these as you migrate)
│   ├── ui/
│   ├── chat/
│   ├── api/
│   └── logs/
└── css/
    ├── variables.css
    ├── base.css
    ├── components/  (create these as you migrate)
    └── features/
```

## How to Use

### Option 1: Gradual Migration (Recommended)

Keep `webui.js` and `webui.css` working, gradually extract modules:

1. Create `static/js/main.js` that imports from both old and new:

   ```javascript
   // Import new modules
   import { state } from "./state.js";
   import { dom, initializeDOMReferences } from "./dom.js";

   // Keep old webui.js functions temporarily
   // Gradually move them to modules
   ```

2. Update functions one at a time
3. Test after each change
4. Remove old files when done

### Option 2: Fresh Start (Advanced)

1. Update `index.html`:

   ```html
   <!-- OLD -->
   <link rel="stylesheet" href="webui.css" />
   <script src="webui.js" defer></script>

   <!-- NEW -->
   <link rel="stylesheet" href="static/css/main.css" />
   <script type="module" src="static/js/main.js"></script>
   ```

2. Create `static/css/main.css`:

   ```css
   @import "./variables.css";
   @import "./base.css";
   /* Import other CSS modules as you create them */
   ```

3. Create `static/js/main.js` (see QUICKSTART.md for example)

## Benefits

| Before                     | After                        |
| -------------------------- | ---------------------------- |
| 1 file, 1500+ lines        | 10-15 files, ~150 lines each |
| Hard to find things        | Clear organization           |
| No IDE autocomplete        | Full autocomplete support    |
| Global namespace pollution | Clean imports                |
| Hard to test               | Easy unit testing            |
| Merge conflicts            | Parallel development         |

## Next Steps

1. **Read** `QUICKSTART.md` for detailed usage examples
2. **Read** `INTEGRATION.md` for HTML integration guide
3. **Read** `../REFACTORING.md` for the full migration plan
4. **Start** extracting feature modules (models, chat, ui, api, logs)
5. **Test** after each module extraction
6. **Update** HTML to use new modular imports
7. **Remove** old monolithic files when migration complete

## Example: Before vs After

### Before (webui.js - line 500)

```javascript
function loadModelList() {
  // 50 lines of tightly coupled code
  // Uses global variables
  // Hard to test
}
```

### After (models/list.js)

```javascript
import { state } from "../state.js";
import { dom } from "../dom.js";

export async function loadModelList() {
  // Same logic, but:
  // - Clear dependencies
  // - Easy to test
  // - Reusable
}
```

## File Size Comparison

| File      | Before         | Target After                   |
| --------- | -------------- | ------------------------------ |
| webui.js  | ~1500 lines    | Deleted                        |
| webui.css | ~1600 lines    | Deleted                        |
| **Total** | **3100 lines** | **~150 lines/file × 20 files** |

## Migration Checklist

- [x] Create directory structure
- [x] Extract constants.js
- [x] Extract state.js
- [x] Extract dom.js
- [x] Extract helpers.js
- [x] Create CSS variables.css
- [x] Create CSS base.css
- [ ] Create main.js entry point
- [ ] Extract models/\* modules
- [ ] Extract chat/\* modules
- [ ] Extract ui/\* modules
- [ ] Extract api/\* modules
- [ ] Extract logs/\* modules
- [ ] Create remaining CSS modules
- [ ] Test all functionality
- [ ] Remove old files
- [ ] Update documentation

## Questions?

- Check `QUICKSTART.md` for usage examples
- Check `../REFACTORING.md` for detailed migration plan
- Each module file has JSDoc comments
- Use ES6 imports/exports throughout

## Maintenance Tips

1. **Keep modules small** - Max 200 lines per file
2. **One responsibility** - Each module does one thing well
3. **Clear imports** - Always import what you need
4. **Test independently** - Write unit tests for each module
5. **Document well** - Use JSDoc comments

Happy refactoring! 🚀
