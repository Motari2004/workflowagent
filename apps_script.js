/**
 * GET handler — test the URL in a browser.
 */
function doGet(e) {
  return ContentService
    .createTextOutput("✅ Script is LIVE! Send a POST request to save data.")
    .setMimeType(ContentService.MimeType.TEXT);
}

/**
 * POST handler — accepts {"content": ...} from HTTP Request node
 *                AND {"value": ...} from Tool node
 *                AND custom {"coin":..., "price":...}
 *
 * Saves: Timestamp | Coin | Price | Content | Raw JSON
 */
function doPost(e) {
  try {
    var data = {};
    if (e && e.postData && e.postData.contents) {
      try { data = JSON.parse(e.postData.contents); }
      catch (_) { data = { content: e.postData.contents }; }
    }

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheets()[0];

    // ---- Extract coin and price ----
    var coin = data.coin || data.symbol || "";
    var price = data.price || "";
    var rawContent = data.content || data.value || data.message || data.details || "";

    // Parse "Current BTC Price: $82,527.67"
    if (rawContent && typeof rawContent === 'string') {
      var coinMatch = rawContent.match(/(?:Current\s+)?([A-Z]{2,10})(?:USDT|\s+Price)/i);
      if (!coin && coinMatch) coin = coinMatch[1].toUpperCase();

      var priceMatch = rawContent.match(/\$?([\d,]+\.?\d*)/);
      if (!price && priceMatch) price = parseFloat(priceMatch[1].replace(/,/g, ''));
    }

    if (price !== "") {
      var num = parseFloat(String(price).replace(/[^\d.-]/g, ''));
      price = isNaN(num) ? price : num;
    }

    if (!coin) coin = "UNKNOWN";
    if (price === "") price = "N/A";

    var row = [
      new Date(),
      coin,
      price,
      rawContent || JSON.stringify(data),
      JSON.stringify(data)
    ];

    sheet.appendRow(row);

    return ContentService
      .createTextOutput(JSON.stringify({
        result: "success",
        saved: { coin: coin, price: price },
        raw: data
      }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService
      .createTextOutput(JSON.stringify({
        result: "error",
        message: error.toString()
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Run ONCE to set column headers.
 */
function setupSheet() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  var headers = [["Timestamp", "Coin", "Price (USD)", "Content", "Raw JSON"]];
  sheet.getRange(1, 1, 1, 5).setValues(headers).setFontWeight("bold");
}
