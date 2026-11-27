// Copy this file to init.js and fill in your local credentials.
// init.js is gitignored and is NEVER served to browsers.
module.exports = {
  "axisstream": {
    "mode": "live",
    "auth_mode": "cookie",
    "email": "",
    "password": ""
  },
  "security": {
    "encryption_key": "",
    "require_api_key": false,
    "rate_limit_rpm": 300
  },
  "erp": {
    "bridge_port": 8001,
    "erp_port": 8088,
    "sync_interval_sec": 15
  }
};
