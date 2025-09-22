// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract SFToken is ERC20 {
    constructor(uint256 initialSupply) ERC20("Smart Fidelity Token", "SFT") {
        _mint(msg.sender, initialSupply);
    }
}

