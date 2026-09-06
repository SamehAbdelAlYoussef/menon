/** @odoo-module **/

import { AccountReportController } from "@account_reports/components/account_report/controller";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

// Clear account_ids on fresh navigation (isOpeningReport=true), keep it during same-page reloads
patch(AccountReportController.prototype, {
    async loadReportOptions(reportId, preloading = false, ignore_session = false, isOpeningReport = false) {
        if (isOpeningReport && !ignore_session && this.hasSessionOptions()) {
            const sessionOpts = { ...this.sessionOptions() };
            if (sessionOpts.account_ids && sessionOpts.account_ids.length) {
                delete sessionOpts.account_ids;
                delete sessionOpts.selected_account_names;
                delete sessionOpts.display_filter_accounts;
                browser.sessionStorage.setItem(this.sessionOptionsID(), JSON.stringify(sessionOpts));
            }
        }
        return super.loadReportOptions(reportId, preloading, ignore_session, isOpeningReport);
    },
});
