frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        relocate_generate_detail_button(frm);
        // Grid buttons can be re-rendered after refresh.
        setTimeout(() => relocate_generate_detail_button(frm), 300);
    },
});

function relocate_generate_detail_button(frm) {
    const grid_field = frm.fields_dict?.custom_towing_kendaraan;
    const grid = grid_field?.grid;

    if (!grid || !grid.wrapper) return;

    const $wrapper = $(grid.wrapper);
    const $grid_buttons = $wrapper.find(".grid-buttons");
    if (!$grid_buttons.length) return;

    const label = __("Generate Detail Kendaraan");
    const button_class = "btn-generate-detail-kendaraan";

    $grid_buttons.find(`.${button_class}`).remove();

    const $existing_form_button = find_existing_generate_button(frm, label);
    if (!$existing_form_button.length) return;

    const $button = $(
        `<button class="btn btn-xs btn-secondary ${button_class}" type="button"></button>`
    ).text(label);

    $button.on("click", () => {
        $existing_form_button.trigger("click");
    });

    const $add_multiple_btn = $grid_buttons.find(".grid-add-multiple-rows");
    if ($add_multiple_btn.length) {
        $button.insertAfter($add_multiple_btn);
    } else {
        $grid_buttons.append($button);
    }

    $existing_form_button.hide();
}

function find_existing_generate_button(frm, label) {
    // Covers custom button in form actions/group button in toolbar.
    const selectors = [
        ".page-form .custom-actions button",
        ".inner-toolbar button",
        ".menu-btn-group button",
    ];

    for (const selector of selectors) {
        const $match = frm.page.wrapper
            .find(selector)
            .filter((_, el) => ($(el).text() || "").trim() === label);
        if ($match.length) return $match.first();
    }

    return $();
}
