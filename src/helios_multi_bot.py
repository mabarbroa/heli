import asyncio
import argparse
import os
import json
from datetime import datetime
from pathlib import Path
import logging
from typing import List, Dict
import sys

from wallet_manager import WalletFileManager
from helios_operations import HeliosOperations

class HeliosMultiBot:
    def __init__(self, batch_number: int = 1, total_batches: int = 3):
        self.batch_number = batch_number
        self.total_batches = total_batches
        self.wallet_manager = WalletFileManager()
        self.helios_ops = HeliosOperations(os.getenv('HELIOS_RPC_URL'))
        self.setup_directories()
        
    def setup_directories(self):
        """Setup direktori untuk logs dan reports"""
        for dir_name in ['logs', 'reports', 'wallets']:
            Path(dir_name).mkdir(exist_ok=True)
    
    async def process_wallet_batch(self, wallets: List[Dict]) -> Dict:
        """Process batch of wallets concurrently"""
        results = {
            'batch_number': self.batch_number,
            'processed': 0,
            'successful_stakes': 0,
            'successful_compounds': 0,
            'total_staked': 0.0,
            'total_compounded': 0.0,
            'errors': 0,
            'transactions': [],
            'wallet_details': []
        }
        
        # Limit concurrent operations untuk avoid rate limiting
        semaphore = asyncio.Semaphore(5)
        
        async def process_single_wallet(wallet):
            async with semaphore:
                return await self.process_wallet_operations(wallet)
        
        logging.info(f"Processing {len(wallets)} wallets in batch {self.batch_number}")
        
        # Process wallets concurrently
        tasks = [process_single_wallet(wallet) for wallet in wallets]
        wallet_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        for i, result in enumerate(wallet_results):
            results['processed'] += 1
            
            if isinstance(result, Exception):
                results['errors'] += 1
                logging.error(f"❌ Wallet {wallets[i]['id']} failed: {result}")
                continue
                
            if result:
                results['wallet_details'].append(result)
                
                if result.get('stake_tx'):
                    results['successful_stakes'] += 1
                    results['total_staked'] += result.get('stake_amount', 0)
                    
                if result.get('compound_tx'):
                    results['successful_compounds'] += 1
                    results['total_compounded'] += result.get('compound_amount', 0)
                    
                if result.get('stake_tx') or result.get('compound_tx'):
                    results['transactions'].append({
                        'wallet_id': result['wallet_id'],
                        'stake_tx': result.get('stake_tx'),
                        'compound_tx': result.get('compound_tx'),
                        'stake_amount': result.get('stake_amount', 0),
                        'compound_amount': result.get('compound_amount', 0)
                    })
        
        return results
    
    async def process_wallet_operations(self, wallet: Dict) -> Dict:
        """Process operations untuk single wallet"""
        result = {
            'wallet_id': wallet['id'],
            'address': wallet['address'],
            'filename': wallet['filename'],
            'initial_balance': 0.0,
            'final_balance': 0.0,
            'stake_tx': None,
            'compound_tx': None,
            'stake_amount': 0.0,
            'compound_amount': 0.0,
            'status': 'pending'
        }
        
        try:
            logging.info(f"🔄 Processing wallet {wallet['id']} ({wallet['address'][:10]}...)")
            
            # Get wallet info
            wallet_info = await self.helios_ops.get_wallet_info(wallet['address'])
            result['initial_balance'] = wallet_info['balance']
            result['pending_rewards'] = wallet_info.get('pending_rewards', 0.0)
            
            # Auto stake jika balance > 1 HLS
            if wallet_info['balance'] > 1.0:
                stake_amount = wallet_info['balance'] * 0.8  # Stake 80% of balance
                logging.info(f"💰 Staking {stake_amount:.4f} HLS from {wallet['id']}")
                
                stake_tx = await self.helios_ops.execute_stake_operation(wallet, stake_amount)
                
                if stake_tx:
                    result['stake_tx'] = stake_tx
                    result['stake_amount'] = stake_amount
                    
                # Small delay after staking
                await asyncio.sleep(2)
            
            # Auto compound rewards jika ada
            if wallet_info.get('pending_rewards', 0) > 0.1:
                logging.info(f"🔄 Compounding rewards for {wallet['id']}")
                compound_tx = await self.helios_ops.execute_auto_compound(wallet)
                
                if compound_tx:
                    result['compound_tx'] = compound_tx
                    result['compound_amount'] = wallet_info['pending_rewards']
            
            # Get final balance
            final_info = await self.helios_ops.get_wallet_info(wallet['address'])
            result['final_balance'] = final_info['balance']
            result['status'] = 'completed'
            
            # Small delay between wallets
            await asyncio.sleep(1)
            
        except Exception as e:
            logging.error(f"❌ Error processing wallet {wallet['id']}: {e}")
            result['status'] = 'error'
            result['error'] = str(e)
            raise
        
        return result
    
    def get_batch_wallets(self, all_wallets: Dict) -> List[Dict]:
        """Get wallets untuk batch tertentu"""
        # Flatten all wallets
        flat_wallets = []
        for filename, wallets in all_wallets.items():
            flat_wallets.extend(wallets)
        
        # Calculate batch size
        total_wallets = len(flat_wallets)
        if total_wallets == 0:
            return []
            
        batch_size = max(1, (total_wallets + self.total_batches - 1) // self.total_batches)
        
        # Get wallets untuk batch ini
        start_idx = (self.batch_number - 1) * batch_size
        end_idx = min(start_idx + batch_size, total_wallets)
        
        batch_wallets = flat_wallets[start_idx:end_idx]
        
        logging.info(f"📊 Batch {self.batch_number}: Processing wallets {start_idx+1}-{end_idx} of {total_wallets}")
        return batch_wallets
    
    async def run_batch(self):
        """Run bot untuk batch tertentu"""
        try:
            logging.info(f"🚀 Starting Helios Multi-Wallet Bot - Batch {self.batch_number}")
            
            # Load all wallets
            all_wallets = self.wallet_manager.load_all_wallet_files()
            
            if not all_wallets:
                logging.error("❌ No wallet files found! Please add .txt files to wallets/ directory")
                # Create sample files
                self.wallet_manager.create_sample_wallet_files()
                return
            
            # Get wallets untuk batch ini
            batch_wallets = self.get_batch_wallets(all_wallets)
            
            if not batch_wallets:
                logging.info(f"ℹ️ No wallets to process in batch {self.batch_number}")
                return
            
            logging.info(f"🔥 Starting batch {self.batch_number} with {len(batch_wallets)} wallets")
            
            # Process batch
            start_time = datetime.now()
            results = await self.process_wallet_batch(batch_wallets)
            end_time = datetime.now()
            
            results['execution_time'] = str(end_time - start_time)
            results['start_time'] = start_time.isoformat()
            results['end_time'] = end_time.isoformat()
            
            # Generate report
            await self.generate_batch_report(results)
            
            # Print summary
            self.print_batch_summary(results)
            
            logging.info(f"✅ Batch {self.batch_number} completed successfully")
            
        except Exception as e:
            logging.error(f"❌ Batch {self.batch_number} failed: {e}")
            raise
    
    def print_batch_summary(self, results: Dict):
        """Print summary ke console untuk GitHub Actions"""
        print("\n" + "="*60)
        print(f"🎯 HELIOS BOT BATCH {results['batch_number']} SUMMARY")
        print("="*60)
        print(f"📊 Wallets Processed: {results['processed']}")
        print(f"✅ Successful Stakes: {results['successful_stakes']}")
        print(f"🔄 Successful Compounds: {results['successful_compounds']}")
        print(f"💰 Total Staked: {results['total_staked']:.4f} HLS")
        print(f"🎁 Total Compounded: {results['total_compounded']:.4f} HLS")
        print(f"❌ Errors: {results['errors']}")
        print(f"⏱️ Execution Time: {results.get('execution_time', 'N/A')}")
        
        if results['transactions']:
            print(f"\n📝 Recent Transactions:")
            for tx in results['transactions'][-5:]:  # Show last 5 transactions
                print(f"  • {tx['wallet_id']}: Stake={tx.get('stake_amount', 0):.4f} HLS")
                
        print("="*60 + "\n")
    
    async def generate_batch_report(self, results: Dict):
        """Generate laporan untuk batch"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"reports/batch_{self.batch_number}_{timestamp}.json"
        latest_file = f"reports/batch_{self.batch_number}_latest.json"
        
        report_data = {
            'batch_number': self.batch_number,
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'wallets_processed': results['processed'],
                'successful_stakes': results['successful_stakes'],
                'successful_compounds': results['successful_compounds'],
                'total_staked_hls': results['total_staked'],
                'total_compounded_hls': results['total_compounded'],
                'errors': results['errors'],
                'execution_time': results.get('execution_time')
            },
            'transactions': results['transactions'],
            'wallet_details': results['wallet_details']
        }
        
        # Save timestamped report
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        # Save latest report (untuk GitHub Actions display)
        with open(latest_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        logging.info(f"📄 Report saved: {report_file}")

async def main():
    parser = argparse.ArgumentParser(description='Helios Multi-Wallet Bot')
    parser.add_argument('--batch', type=int, default=1, help='Batch number to process')
    parser.add_argument('--total-batches', type=int, default=3, help='Total number of batches')
    
    args = parser.parse_args()
    
    # Force run jika ada environment variable
    force_run = os.getenv('FORCE_RUN', 'false').lower() == 'true'
    
    if force_run:
        logging.info("🔥 Force run enabled")
    
    bot = HeliosMultiBot(args.batch, args.total_batches)
    await bot.run_batch()

if __name__ == "__main__":
    asyncio.run(main())
