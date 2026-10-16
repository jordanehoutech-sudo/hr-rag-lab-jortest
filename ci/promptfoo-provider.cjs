const fs = require('fs');
const path = require('path');
module.exports = class CapturedApiProvider {
  id() { return 'captured-authenticated-hr-api'; }
  async callApi(prompt, context) {
    const report = JSON.parse(fs.readFileSync(path.join(__dirname, '../build/evaluation.json'), 'utf8'));
    const rows = report.records.filter(r => r.case_id === String(context.vars.case_id));
    if (!rows.length || rows.some(r => typeof r.answer !== 'string' || r.error)) {
      return {error: 'Required real API output is missing'};
    }
    return {output: JSON.stringify(rows)};
  }
};
