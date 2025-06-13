import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
import json
from datetime import datetime

class WalletFileManager:
    def __init__(self, wallets_dir="wallets"):
        self.wallets_dir = Path(wallets_dir)
        self.wallets_dir.mkdir(exist_ok=True)
        self.setup_logging()
        
    def setup_logging(self):
        """Setup logging untuk GitHub Actions"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'logs/helios_bot_{datetime.now().strftime("%Y%m%d")}.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_wallets_from_txt(self, filename: str) -> List[Dict]:
        """Load private keys dari file .txt"""
        file_path = self.wallets_dir / filename
        wallets = []
        
        if not file_path.exists():
            self.logger.error(f"Wallet file not found: {file_path}")
            return []
        
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                line = line.strip()
                if line and not line.startswith('#'):  # Skip comments and empty lines
                    try:
                        # Validate private key
                        if line.startswith('0x'):
                            private_key = line
                        else:
                            private_key = '0x' + line
                            
                        account = Account.from_key(private_key)
                        wallet_config = {
                            'id': f"{filename.replace('.txt', '')}_{i+1}",
                            'private_key': private_key,
                            'address': account.address,
                            'filename': filename,
                            'line_number': i+1
                        }
                        wallets.append(wallet_config)
                        
                    except Exception as e:
                        self.logger.error(f"Invalid private key at line {i+1} in {filename}: {e}")
                        
            self.logger.info(f"Loaded {len(wallets)} valid wallets from {filename}")
            return wallets
            
        except Exception as e:
            self.logger.error(f"Error reading wallet file {filename}: {e}")
            return []
    
    def load_all_wallet_files(self) -> Dict[str, List[Dict]]:
        """Load semua file .txt dalam folder wallets"""
        all_wallets = {}
        
        txt_files = list(self.wallets_dir.glob("*.txt"))
        if not txt_files:
            self.logger.warning(f"No .txt files found in {self.wallets_dir}")
            return {}
        
        for txt_file in txt_files:
            filename = txt_file.name
            wallets = self.load_wallets_from_txt(filename)
            if wallets:
                all_wallets[filename] = wallets
                
        total_wallets = sum(len(wallets) for wallets in all_wallets.values())
        self.logger.info(f"Total loaded: {total_wallets} wallets from {len(all_wallets)} files")
        
        return all_wallets
    
    def split_wallets_into_batches(self, all_wallets: Dict, batch_size: int = 50) -> List[List[Dict]]:
        """Split wallets menjadi batches untuk parallel processing"""
        flat_wallets = []
        for filename, wallets in all_wallets.items():
            flat_wallets.extend(wallets)
        
        batches = []
        for i in range(0, len(flat_wallets), batch_size):
            batch = flat_wallets[i:i + batch_size]
            batches.append(batch)
            
        self.logger.info(f"Split {len(flat_wallets)} wallets into {len(batches)} batches")
        return batches
    
    def create_sample_wallet_files(self):
        """Create sample wallet files untuk testing"""
        sample_files = {
            'main_wallets.txt': [
                '# Main wallet private keys - one per line',
                '# Lines starting with # are ignored',
                'your_private_key_1_here',
                'your_private_key_2_here'
            ],
            'backup_wallets.txt': [
                '# Backup wallet private keys',
                'your_private_key_3_here',
                'your_private_key_4_here'
            ]
        }
        
        for filename, content in sample_files.items():
            file_path = self.wallets_dir / filename
            if not file_path.exists():
                with open(file_path, 'w') as f:
                    f.write('\n'.join(content))
                self.logger.info(f"Created sample file: {filename}")
