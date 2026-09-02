# 📜 Smart Contract Verification Guide

This guide explains how to manually verify the `IdentityRegistry.sol` smart contract on Sepolia Etherscan using Remix IDE. This is necessary because the contract uses OpenZeppelin `AccessControl`, which consists of multiple dependencies that Etherscan needs in order to match the deployed bytecode.

**Contract Address:** `0x547c457d9c1d7d52825d4e0d9cd56cff5d527f58`
**Network:** Sepolia Testnet

---

## Step 1: Flatten the Contract using Remix

1. Open [Remix IDE](https://remix.ethereum.org/) in your browser.
2. In the **File Explorers** pane, create a new file named `IdentityRegistry.sol`.
3. Paste the complete contents of `contracts/IdentityRegistry.sol` from your local codebase into this new file.
4. If it prompts you to install missing dependencies (like `@openzeppelin/contracts`), let Remix automatically fetch them. You can also right-click and compile to ensure it downloads the OpenZeppelin imports.
5. In the **File Explorers** pane, right-click on `IdentityRegistry.sol` and select **"Flatten"**. 
6. Remix will generate a new file named `IdentityRegistry_flattened.sol` (or similar). This file contains your contract along with all the OpenZeppelin code combined into a single file.
7. Open the flattened file and copy all of its contents to your clipboard.
    * **Note:** You may need to remove duplicate `// SPDX-License-Identifier: MIT` lines or `pragma solidity` statements at the top of the flattened file to prevent compiler warnings on Etherscan. Keep only one at the very top.

---

## Step 2: Verify on Etherscan

1. Navigate to the exact verification URL for your deployed contract:
   **[Verify 0x24fc47...170Ec on Sepolia Etherscan](https://sepolia.etherscan.io/verifyContract?address=0x24fc4768834e6066D66F105522D47Ad591B170Ec)**
2. Fill out the initial form:
   * **Compiler Type:** `Solidity (Single file)`
   * **Compiler Version:** `v0.8.24+commit.e11b9ed9`
   * **Open Source License Type:** `MIT License (MIT)`
3. Click **Continue**.
4. On the next page, paste your flattened code (from Step 1) into the **"Enter the Solidity Contract Code below"** text box.
5. (Optional) Check the **Optimization** setting. If you deployed using `deploy.py`, optimization was not explicitly enabled, so leave it as `No`.
6. Complete the CAPTCHA and click **Verify and Publish**.

---

## Expected Result

Once Etherscan processes the code, you will see a green checkmark ✅ and a success message: **"Contract Source Code Verified"**.

Anyone can now visit your contract's page on Etherscan, click the **Contract** tab, and read the verified Solidity source code alongside the ABI!
