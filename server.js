const express = require('express');
const axios = require('axios');
const path = require('path');
const app = express();

app.use(express.json());
app.use(express.static('public'));

// The "Execution Engine"
app.post('/run', async (req, res) => {
    const { nodes } = req.body;
    const logs = [];
    let finalData = null;

    console.log("\n--- 🚀 NEW EXECUTION STARTED ---");
    console.log("📩 Received Payload:", JSON.stringify(nodes, null, 2));

    if (!nodes || nodes.length === 0) {
        console.log("❌ ERROR: No nodes received!");
        return res.status(400).json({ status: "error", logs: ["No nodes provided"], data: null });
    }

    try {
        let currentMemory = "";

        for (let i = 0; i < nodes.length; i++) {
            const node = nodes[i];
            console.log(`⚙️  Processing Node [${i}]: ${node.type}...`);
            logs.push(`Executing node: ${node.type}...`);

            if (node.type === 'market-data') {
                const coin = node.data.coin || 'bitcoin';
                console.log(`   🔍 Fetching price for ${coin}...`);
                
                // Real API call to Binance
                const response = await axios.get(`https://api.binance.com/api/v3/ticker/price?symbol=${coin.toUpperCase()}USDT`);
                const price = parseFloat(response.data.price).toFixed(2);
                
                currentMemory = `Current ${coin.toUpperCase()} Price: $${price}`;
                logs.push(`Success: ${currentMemory}`);
                console.log(`   ✅ Got Price: ${price}`);

            } else if (node.type === 'filter') {
                const keyword = node.data.keyword || 'Price';
                console.log(`   🔍 Filtering for keyword: "${keyword}"...`);
                
                if (currentMemory.includes(keyword)) {
                    currentMemory = `[VALIDATED] ${currentMemory}`;
                    logs.push(`Filter matched: "${keyword}"`);
                    console.log(`   ✅ Match found!`);
                } else {
                    currentMemory = `[REJECTED] No match for ${keyword}`;
                    logs.push(`Filter failed: "${keyword}" not found`);
                    console.log(`   ⚠️ No match.`);
                }

            } else if (node.type === 'console') {
                console.log(`   🖥️  Outputting to terminal...`);
                logs.push(`Finalizing output: ${currentMemory}`);
                finalData = currentMemory;
            }
        }

        console.log("🏁 Execution Complete. Sending response...");
        res.json({ status: "success", logs: logs, data: finalData });

    } catch (error) {
        console.error("🚨 CRITICAL ERROR:", error.message);
        res.status(500).json({ status: "error", logs: [`System Error: ${error.message}`], data: null });
    }
});

const PORT = 3000;
app.listen(PORT, () => {
    console.log(`\n=======================================`);
    console.log(`🌟 WORKFLOW ENGINE ONLINE`);
    console.log(`🌐 Dashboard: http://localhost:${PORT}`);
    console.log(`=======================================\n`);
});
