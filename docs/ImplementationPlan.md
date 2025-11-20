### Phase 1: Data Transformation Layer
**Goal:** Convert OpenAI formatted tools into the JSON structure expected by the AI Studio "Code Editor" text area.

1.  **Create `api_utils/tool_converter.py`**
    The AI Studio Code Editor expects a simple list of function objects, not wrapped in `{"type": "function", "function": {...}}` like OpenAI.

    ```python
    # api_utils/tool_converter.py
    import json

    def convert_to_gemini_schema(openai_tools):
        """
        Converts OpenAI tool definitions to Gemini AI Studio JSON format.
        """
        gemini_tools = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                fn = tool.get("function", {})
                gemini_tool = {
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {})
                }
                gemini_tools.append(gemini_tool)
        return json.dumps(gemini_tools, indent=2)
    ```

---

### Phase 2: Browser Automation (Playwright)
**Goal:** Implement the `set_function_declarations` method in `PageController`. This is the most critical part involving the selectors you provided.

**File:** `browser_utils/page_controller.py`

**Logic:**
1.  Locate the Function Calling section (usually in the right sidebar or settings).
2.  Ensure the toggle is ON.
3.  Click "Edit".
4.  Switch to "Code Editor".
5.  Paste the JSON.
6.  Save.

**Implementation Draft:**

```python
    # Add to PageController class in browser_utils/page_controller.py

    async def set_function_declarations(self, tools_json: str):
        """
        Manually interacts with the AI Studio UI to set function definitions.
        """
        try:
            # 1. Handle the Toggle Switch
            # Selector based on: <mat-slide-toggle ... class="function-calling-toggle ...">
            toggle_btn = self.page.locator('.function-calling-toggle button[role="switch"]')
            
            # Check if it exists (sidebar might be collapsed, logic might need to open sidebar first)
            if await toggle_btn.count() > 0:
                is_checked = await toggle_btn.get_attribute("aria-checked") == "true"
                if not is_checked:
                    await toggle_btn.click()
                    # Wait for the toggle to animate/activate
                    await self.page.wait_for_timeout(500) 

            # 2. Click the "Edit" button
            # Selector: <button ... class="edit-function-declarations-button ...">
            edit_btn = self.page.locator('button.edit-function-declarations-button')
            await edit_btn.click()

            # 3. Wait for Dialog
            # Selector: <ms-edit-function-declarations-dialog ...>
            dialog = self.page.locator('ms-edit-function-declarations-dialog')
            await dialog.wait_for(state="visible", timeout=3000)

            # 4. Switch to "Code Editor" Tab
            # Selector logic: Find button inside tab group with specific text
            code_editor_tab = dialog.locator('div[role="tablist"] button[role="tab"]', has_text="Code Editor")
            
            # Check if it's already selected to avoid unnecessary clicks
            is_tab_selected = await code_editor_tab.get_attribute("aria-selected") == "true"
            if not is_tab_selected:
                await code_editor_tab.click()
                await self.page.wait_for_timeout(300)

            # 5. Input the JSON into the Text Area
            # Selector: <ms-text-editor ...> <textarea ...>
            textarea = dialog.locator('ms-text-editor textarea')
            await textarea.click()
            await textarea.fill(tools_json)

            # 6. Click Save
            # Selector: Dialog actions -> Save button
            # <button ... class="ms-button-primary"> Save </button>
            save_btn = dialog.locator('.mat-mdc-dialog-actions button.ms-button-primary', has_text="Save")
            await save_btn.click()

            # 7. Wait for Dialog to close
            await dialog.wait_for(state="hidden", timeout=3000)
            
            self.logger.info("Successfully updated function declarations via native UI.")

        except Exception as e:
            self.logger.error(f"Failed to set function declarations: {e}")
            # Depending on severity, might want to raise or fallback
```

---

### Phase 3: Orchestration & Logic Updates
**Goal:** Wire the new automation method into the request lifecycle.

1.  **Modify `api_utils/utils.py`**:
    *   Update `prepare_combined_prompt`.
    *   **CRITICAL:** If `tools` are present in the request, **DO NOT** append the text-based tool prompt string to the user message. Return a flag or separate object indicating native tools are active.

2.  **Modify `api_utils/request_processor.py`**:
    *   In `process_request` (or where `page_controller` is called), check if `request.tools` exists.
    *   Before calling `page_controller.submit_prompt(...)`:
        *   Call the new `convert_to_gemini_schema`.
        *   Call `await page_controller.set_function_declarations(converted_json)`.
    *   *Edge Case:* If the request has *no* tools, but the previous request *did*, you might need to clear the settings in the UI (pass empty JSON `[]`).

---

### Phase 4: Response Handling (The Return Trip)
**Goal:** Detect when AI Studio performs a tool call and parse it.

*   **Visual Indicator:** When AI Studio calls a function, it typically creates a distinct UI block in the chat stream (separate from standard markdown text).
*   **Streaming Path:** You will need to inspect the network stream (in `_handle_auxiliary_stream_response`) for specific event types related to `functionCall` or `toolUse`.
*   **Playwright Fallback:** In `get_response`, you will need a new selector to find the "Function Call" bubble.
    *   *Action:* If the specific "Function Call" bubble is detected in the DOM, parse its content.
    *   *Output:* Construct an OpenAI `tool_calls` response object.

### Summary of Execution Order

1.  **Request Received:** `tools=[...]` is present.
2.  **Pre-processing:** Convert to `[{"name": "...", ...}]`.
3.  **Browser Action:** Playwright opens settings -> toggles ON -> Edit -> Code Editor -> Paste JSON -> Save.
4.  **Prompt Action:** Playwright types the *user prompt only* (no tool definitions in text).
5.  **Execution:** Gemini decides to call a tool.
6.  **Response Parsing:** Proxy detects the tool call structure, formats it as OpenAI JSON, and returns it to the client.