import asyncio
import aiohttp
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
import json
import time
from typing import Dict, List, Optional
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

class HeliosOperations:
    def __init__(self, rpc_url: str = None):
        self.rpc_url = rpc_url or "https://testnet1.helioschainlabs.org"
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Helios contract addresses (update dengan address yang benar)
        self.contracts = {
            'staking': '0x007a1123a54cdD9bA35AD2012DB086b9d8350A5f',
            'bridge': '0x1234567890123456789012345678901234567890',  # Update dengan address yang benar
            'rewards': '0x1234567890123456789012345678901234567890'  # Update dengan address yang benar
        }
        
        self.logger = logging.getLogger(__name__)
        
        # Test connection
        try:
            chain_id = self.w3.eth.chain_id
            self.logger.info(f"Connected to Helios network, Chain ID: {chain_id}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Helios network: {e}")
        
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_wallet_balance(self, address: str) -> float:
        """Get wallet balance dengan retry mechanism"""
        try:
            balance_wei = self.w3.eth.get_balance(address)
            balance_eth = self.w3.from_wei(balance_wei, 'ether')
            return float(balance_eth)
        except Exception as e:
            self.logger.error(f"Error getting balance for {address}: {e}")
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_stake_operation(self, wallet: Dict, stake_amount: float) -> Optional[str]:
        """Execute staking operation"""
        try:
            account = Account.from_key(wallet['private_key'])
            stake_amount_wei = self.w3.to_wei(stake_amount, 'ether')
            
            # Build staking transaction
            nonce = self.w3.eth.get_transaction_count(account.address)
            gas_price = self.w3.eth.gas_price
            
            # Limit gas price untuk efisiensi
            max_gas_price = self.w3.to_wei('25', 'gwei')
            if gas_price > max_gas_price:
                self.logger.warning(f"Gas price too high: {self.w3.from_wei(gas_price, 'gwei')} gwei")
                return None
            
            # Simple transfer to staking contract (adjust sesuai dengan staking method)
            stake_tx = {
                'to': self.contracts['staking'],
                'value': stake_amount_wei,
                'gas': 150000,
                'gasPrice': min(gas_price, max_gas_price),
                'nonce': nonce,
                'chainId': self.w3.eth.chain_id
            }
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(stake_tx, wallet['private_key'])
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                self.logger.info(f"✅ Staked {stake_amount} HLS from {wallet['id']} - TX: {tx_hash.hex()}")
                return tx_hash.hex()
            else:
                self.logger.error(f"❌ Stake transaction failed for {wallet['id']} - TX: {tx_hash.hex()}")
                return None
            
        except Exception as e:
            self.logger.error(f"Stake error for {wallet['id']}: {e}")
            return None
    
    async def execute_auto_compound(self, wallet: Dict) -> Optional[str]:
        """Execute auto compound rewards"""
        try:
            # Check pending rewards
            pending_rewards = await self.get_pending_rewards(wallet['address'])
            
            if pending_rewards > 0.1:  # Minimum 0.1 HLS untuk compound
                account = Account.from_key(wallet['private_key'])
                
                # Build compound transaction (adjust sesuai dengan compound method)
                compound_tx = {
                    'to': self.contracts['rewards'],
                    'value': 0,
                    'gas': 100000,
                    'gasPrice': self.w3.eth.gas_price,
                    'nonce': self.w3.eth.get_transaction_count(account.address),
                    'chainId': self.w3.eth.chain_id,
                    'data': '0x'  # Add compound function call data here
                }
                
                signed_tx = self.w3.eth.account.sign_transaction(compound_tx, wallet['private_key'])
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                
                if receipt.status == 1:
                    self.logger.info(f"✅ Compounded {pending_rewards} HLS for {wallet['id']} - TX: {tx_hash.hex()}")
                    return tx_hash.hex()
                else:
                    self.logger.error(f"❌ Compound failed for {wallet['id']} - TX: {tx_hash.hex()}")
                    return None
                
        except Exception as e:
            self.logger.error(f"Compound error for {wallet['id']}: {e}")
            return None
    
    async def get_pending_rewards(self, address: str) -> float:
        """Get pending staking rewards"""
        try:
            # Placeholder - implement sesuai dengan Helios staking contract
            # Contoh: call contract method untuk get pending rewards
            return 0.0
        except Exception as e:
            self.logger.error(f"Error getting rewards for {address}: {e}")
            return 0.0
    
    async def execute_bridge_operation(self, wallet: Dict, amount: float, target_chain: str) -> Optional[str]:
        """Execute bridge operation ke chain lain"""
        try:
            account = Account.from_key(wallet['private_key'])
            
            bridge_tx = {
                'to': self.contracts['bridge'],
                'value': self.w3.to_wei(amount, 'ether'),
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(account.address),
                'chainId': self.w3.eth.chain_id,
                'data': '0x'  # Add bridge function call data here
            }
            
            signed_tx = self.w3.eth.account.sign_transaction(bridge_tx, wallet['private_key'])
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                self.logger.info(f"✅ Bridged {amount} HLS from {wallet['id']} to {target_chain} - TX: {tx_hash.hex()}")
                return tx_hash.hex()
            else:
                self.logger.error(f"❌ Bridge failed for {wallet['id']} - TX: {tx_hash.hex()}")
                return None
            
        except Exception as e:
            self.logger.error(f"Bridge error for {wallet['id']}: {e}")
            return None
    
    async def get_wallet_info(self, address: str) -> Dict:
        """Get comprehensive wallet information"""
        try:
            balance = await self.get_wallet_balance(address)
            pending_rewards = await self.get_pending_rewards(address)
            
            return {
                'address': address,
                'balance': balance,
                'pending_rewards': pending_rewards,
                'total_value': balance + pending_rewards
            }
        except Exception as e:
            self.logger.error(f"Error getting wallet info for {address}: {e}")
            return {
                'address': address,
                'balance': 0.0,
                'pending_rewards': 0.0,
                'total_value': 0.0,
                'error': str(e)
            }
