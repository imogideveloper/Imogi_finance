frappe.provide("imogi_finance.workspace_visibility");

const normalize_label = (label) => (label || "").trim().toLowerCase();

imogi_finance.workspace_visibility.get_hidden_labels = function (workspaceName) {
	const bootMap = frappe.boot.imogi_workspace_hidden || {};
	const fromBoot = bootMap[workspaceName] || [];
	const fromPage = (frappe.workspace_page_data_hidden || {})[workspaceName] || [];
	return [...new Set([...fromBoot, ...fromPage])];
};

imogi_finance.workspace_visibility.filter_content = function (content, hiddenLabels) {
	if (!content || !hiddenLabels || !hiddenLabels.length) {
		return content;
	}

	const hidden = new Set(hiddenLabels.map(normalize_label));

	return content.filter((block) => {
		const data = block.data || {};
		if (block.type === "shortcut") {
			return !hidden.has(normalize_label(data.shortcut_name));
		}
		if (block.type === "card") {
			return !hidden.has(normalize_label(data.card_name));
		}
		return true;
	});
};

imogi_finance.workspace_visibility.filter_page_data = function (pageData, hiddenLabels) {
	if (!pageData || !hiddenLabels || !hiddenLabels.length) {
		return pageData;
	}

	const hidden = new Set(hiddenLabels.map(normalize_label));

	if (pageData.cards && pageData.cards.items) {
		pageData.cards.items = pageData.cards.items.filter(
			(card) => !hidden.has(normalize_label(card.label))
		);
	}

	if (pageData.shortcuts && pageData.shortcuts.items) {
		pageData.shortcuts.items = pageData.shortcuts.items.filter(
			(item) => !hidden.has(normalize_label(item.label))
		);
	}

	pageData.hidden_sections = hiddenLabels;
	return pageData;
};

imogi_finance.workspace_visibility.apply = function (workspaceView) {
	if (!workspaceView) {
		return;
	}

	const workspaceName =
		(workspaceView._page && workspaceView._page.title) ||
		workspaceView.page_name ||
		"";

	const hidden = imogi_finance.workspace_visibility.get_hidden_labels(workspaceName);
	if (!hidden.length) {
		return;
	}

	if (workspaceView.content && workspaceView.content.length) {
		workspaceView.content = imogi_finance.workspace_visibility.filter_content(
			workspaceView.content,
			hidden
		);
	}

	if (workspaceView.page_data) {
		imogi_finance.workspace_visibility.filter_page_data(workspaceView.page_data, hidden);
	}
};

imogi_finance.workspace_visibility.patch_workspace_view = function () {
	if (!frappe.views || !frappe.views.Workspace) {
		return false;
	}

	const Workspace = frappe.views.Workspace;
	if (Workspace.__imogi_visibility_patched) {
		return true;
	}
	Workspace.__imogi_visibility_patched = true;

	const original_prepare = Workspace.prototype.prepare_editorjs;
	Workspace.prototype.prepare_editorjs = function () {
		imogi_finance.workspace_visibility.apply(this);
		const workspaceName = (this._page && this._page.title) || "";
		const result = original_prepare.apply(this, arguments);
		setTimeout(() => {
			imogi_finance.workspace_visibility.hide_dom_sections(workspaceName);
		}, 800);
		return result;
	};

	const original_get_data = Workspace.prototype.get_data;
	Workspace.prototype.get_data = function (page) {
		return original_get_data.call(this, page).then((result) => {
			imogi_finance.workspace_visibility.apply(this);
			if (page && page.name && this.page_data) {
				this.pages[page.name] = this.page_data;
			}
			return result;
		});
	};

	const original_show = Workspace.prototype.show_page;
	Workspace.prototype.show_page = async function (page) {
		if (this.pages && this.pages[page.name]) {
			delete this.pages[page.name];
		}
		return original_show.call(this, page);
	};

	return true;
};

imogi_finance.workspace_visibility.hide_dom_sections = function (workspaceName) {
	const hidden = imogi_finance.workspace_visibility.get_hidden_labels(workspaceName);
	if (!hidden.length) {
		return;
	}
	const hiddenSet = new Set(hidden.map(normalize_label));
	document.querySelectorAll(".widget-group-title").forEach((el) => {
		const title = normalize_label(el.textContent);
		if (!hiddenSet.has(title)) {
			return;
		}
		const group = el.closest(".widget-group");
		if (group) {
			group.style.display = "none";
		}
	});
};

(function () {
	const tryPatch = () => imogi_finance.workspace_visibility.patch_workspace_view();
	if (!tryPatch()) {
		frappe.ready(tryPatch);
	}

	frappe.router.on("change", () => {
		setTimeout(() => {
			const route = frappe.get_route();
			let workspaceName = null;
			if (route[0] === "Workspaces") {
				workspaceName = route[1] === "private" ? route[2] : route[1];
			} else if (frappe.workspaces && frappe.workspaces[route[0]]) {
				workspaceName = frappe.workspaces[route[0]].title;
			}
			if (workspaceName) {
				imogi_finance.workspace_visibility.hide_dom_sections(workspaceName);
			}
		}, 1200);
	});
})();
