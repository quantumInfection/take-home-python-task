import logging
import asyncio
from typing import Optional, Dict, Any, List, Union
import bittensor
from bittensor.core.async_subtensor import AsyncSubtensor

from app.core.config import settings

logger = logging.getLogger(__name__)


class BlockchainService:
    """Service for interacting with the Bittensor blockchain."""

    def __init__(self):
        """Initialize AsyncSubtensor connection."""
        self._subtensor = None
        self._wallet = None

    async def get_subtensor(self) -> AsyncSubtensor:
        """
        Get or initialize AsyncSubtensor instance.
        Uses lazy initialization for better async handling.
        """
        if self._subtensor is None:
            logger.info(
                f"Initializing AsyncSubtensor for network: {settings.BITTENSOR_NETWORK}"
            )

            try:
                # Use AsyncSubtensor as specified in the requirements
                if settings.BITTENSOR_NETWORK == "local":
                    self._subtensor = AsyncSubtensor(
                        chain_endpoint="ws://host.docker.internal:9944",
                    )
                elif settings.BITTENSOR_NETWORK == "test":
                    # For testnet (as required by the task)
                    self._subtensor = AsyncSubtensor(
                        network="test",
                    )
                elif settings.BITTENSOR_NETWORK == "finney":
                    self._subtensor = AsyncSubtensor(
                        network="finney",
                    )
                else:
                    # Default to testnet as specified in the requirements
                    self._subtensor = AsyncSubtensor(
                        network="test",
                    )

                logger.info(
                    f"AsyncSubtensor initialized for {settings.BITTENSOR_NETWORK} network"
                )
            except Exception as e:
                logger.error(f"Error initializing AsyncSubtensor: {str(e)}")
                raise

        return self._subtensor

    def get_wallet(self) -> bittensor.wallet:
        """
        Get or initialize Bittensor wallet.
        Uses mnemonic from settings.
        """
        if self._wallet is None:
            logger.info(
                f"Initializing Bittensor wallet: {settings.BITTENSOR_WALLET_NAME}/{settings.BITTENSOR_WALLET_HOTKEY}"
            )
            self._wallet = bittensor.wallet(
                name=settings.BITTENSOR_WALLET_NAME,
                hotkey=settings.BITTENSOR_WALLET_HOTKEY,
            )

            # Regenerate the wallet if mnemonic is provided
            if settings.BITTENSOR_WALLET_MNEMONIC:
                logger.info("Regenerating wallet using provided mnemonic")
                self._wallet.regenerate_coldkeypub(
                    mnemonic=settings.BITTENSOR_WALLET_MNEMONIC
                )

            logger.info(f"Wallet initialized: {self._wallet.coldkeypub.ss58_address}")
        return self._wallet

    async def get_tao_dividends(
        self, netuid: Optional[int], hotkey: Optional[str]
    ) -> Dict[str, Any]:
        """
        Query the blockchain for Tao dividends specifically using TaoDividendsPerSubnet.

        Args:
            netuid: Subnet ID
            hotkey: Account hotkey

        Returns:
            Dictionary with dividend data. If hotkey is None, returns a list under 'dividends'.
        """
        subtensor = await self.get_subtensor()

        # Use default values if not provided
        actual_netuid = netuid if netuid is not None else settings.DEFAULT_NETUID
        actual_hotkey = hotkey if hotkey is not None else settings.DEFAULT_HOTKEY

        try:
            logger.info(
                f"Querying TaoDividendsPerSubnet for netuid={actual_netuid}, hotkey={actual_hotkey}"
            )

            if hotkey is None:
                # If hotkey is not provided, get dividends for all hotkeys in the subnet
                metagraph = await subtensor.metagraph(netuid=actual_netuid)

                results = []
                for uid, neuron_hotkey in enumerate(metagraph.hotkeys):
                    try:
                        # Use direct substrate interface to query TaoDividendsPerSubnet
                        dividend_query_result = await subtensor.substrate.query_map(
                            module="SubtensorModule",
                            storage_function="TaoDividendsPerSubnet",
                            params=[actual_netuid, neuron_hotkey],
                        )
                        # Log the raw result for debugging
                        logger.debug(
                            f"Raw query_map result for {neuron_hotkey}: {dividend_query_result!r}"
                        )  # Added logging

                        dividend_value = 0.0
                        # Refined extraction logic with better checks
                        if (
                            dividend_query_result
                            and isinstance(dividend_query_result, list)
                            and len(dividend_query_result) > 0
                        ):
                            # Assuming the structure is like [(key_info, value_object)]
                            value_object = dividend_query_result[0][
                                1
                            ]  # Check index 1 for value
                            if value_object and hasattr(value_object, "value"):
                                # Convert to float, handle potential None value explicitly
                                raw_value = value_object.value
                                # Check if raw_value is not None before converting to float
                                dividend_value = (
                                    float(raw_value) if raw_value is not None else 0.0
                                )
                            else:
                                logger.warning(
                                    f"Value object for {neuron_hotkey} has unexpected structure or no 'value' attribute: {value_object!r}"
                                )
                        elif dividend_query_result:
                            logger.warning(
                                f"query_map result for {neuron_hotkey} has unexpected structure: {dividend_query_result!r}"
                            )

                        # Simplified response item, removing uid
                        results.append(
                            {
                                "netuid": actual_netuid,
                                "hotkey": neuron_hotkey,
                                "dividend": dividend_value,  # Use the extracted value
                            }
                        )
                    except Exception as e:
                        logger.warning(
                            f"Error fetching dividend for {neuron_hotkey}: {str(e)}"
                        )

                # Simplified response structure for multiple hotkeys
                return {
                    "netuid": actual_netuid,
                    "dividends": results,
                }
            else:
                # Query dividend for specific hotkey
                dividend_query_result = await subtensor.substrate.query(
                    module="SubtensorModule",
                    storage_function="TaoDividendsPerSubnet",
                    params=[actual_netuid, actual_hotkey],
                )
                # Log the raw result for debugging
                logger.debug(
                    f"Raw query result for {actual_hotkey}: {dividend_query_result!r}"
                )  # Added logging

                dividend_value = 0.0
                # Refined extraction logic
                if dividend_query_result and hasattr(dividend_query_result, "value"):
                    # Convert to float, handle potential None value explicitly
                    raw_value = dividend_query_result.value
                    # Check if raw_value is not None before converting to float
                    dividend_value = float(raw_value) if raw_value is not None else 0.0
                elif dividend_query_result:
                    logger.warning(
                        f"Query result for {actual_hotkey} has no 'value' attribute: {dividend_query_result!r}"
                    )

                # Response for single hotkey matches core fields of README example
                return {
                    "netuid": actual_netuid,
                    "hotkey": actual_hotkey,
                    "dividend": dividend_value,  # Use the extracted value
                }

        except Exception as e:
            logger.error(f"Error querying blockchain: {str(e)}", exc_info=True)
            raise

    async def add_stake(
        self, netuid: int, hotkey: str, amount: float
    ) -> Dict[str, Any]:
        """
        Add stake to a hotkey on a subnet.

        Args:
            netuid: Subnet ID
            hotkey: Account hotkey
            amount: Amount of TAO to stake

        Returns:
            Transaction result
        """
        subtensor = await self.get_subtensor()
        wallet = self.get_wallet()

        try:
            logger.info(f"Adding stake: {amount} TAO to {hotkey} on subnet {netuid}")

            # Convert amount to rao (blockchain unit) - 1 TAO = 10^9 rao
            amount_rao = int(amount * 1e9)

            # Use AsyncSubtensor's add_stake method as specified in the requirements
            response = await subtensor.add_stake(
                wallet=wallet,
                hotkey_ss58=hotkey,
                amount=amount_rao,
            )

            return {
                "success": True,
                "operation": "add_stake",
                "netuid": netuid,
                "hotkey": hotkey,
                "amount": amount,
                "hash": str(response.hash) if response else None,
            }

        except Exception as e:
            logger.error(f"Error adding stake: {str(e)}", exc_info=True)
            return {
                "success": False,
                "operation": "add_stake",
                "netuid": netuid,
                "hotkey": hotkey,
                "amount": amount,
                "error": str(e),
            }

    async def unstake(self, netuid: int, hotkey: str, amount: float) -> Dict[str, Any]:
        """
        Unstake from a hotkey on a subnet.

        Args:
            netuid: Subnet ID
            hotkey: Account hotkey
            amount: Amount of TAO to unstake

        Returns:
            Transaction result
        """
        subtensor = await self.get_subtensor()
        wallet = self.get_wallet()

        try:
            logger.info(f"Unstaking: {amount} TAO from {hotkey} on subnet {netuid}")

            # Convert amount to rao (blockchain unit) - 1 TAO = 10^9 rao
            amount_rao = int(amount * 1e9)

            # Use AsyncSubtensor's unstake method as specified in the requirements
            response = await subtensor.unstake(
                wallet=wallet,
                hotkey_ss58=hotkey,
                amount=amount_rao,
            )

            return {
                "success": True,
                "operation": "unstake",
                "netuid": netuid,
                "hotkey": hotkey,
                "amount": amount,
                "hash": str(response.hash) if response else None,
            }

        except Exception as e:
            logger.error(f"Error unstaking: {str(e)}", exc_info=True)
            return {
                "success": False,
                "operation": "unstake",
                "netuid": netuid,
                "hotkey": hotkey,
                "amount": amount,
                "error": str(e),
            }
