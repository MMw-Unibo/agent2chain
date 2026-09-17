export function extractContractName(source) {
  if (typeof source !== "string") {
    return "";
  }
  const noComments = source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
  const match = noComments.match(/\bcontract\s+([A-Za-z_][A-Za-z0-9_]*)/);
  return match ? match[1] : "";
}

export function parseConstructorArgs(rawArgs) {
  const raw = String(rawArgs || "").trim();
  if (!raw) {
    return [];
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("Constructor arguments must be valid JSON.");
  }

  if (!Array.isArray(parsed)) {
    throw new Error("Constructor arguments must be a JSON array.");
  }

  return parsed;
}

export async function deployCompiledContract({
  deployData,
  constructorArgs,
  addMessage,
  onTransactionSent,
}) {
  const ethersLib = window?.ethers;
  if (!ethersLib) {
    throw new Error("Ethers library not available in UI runtime.");
  }

  if (!window.ethereum) {
    throw new Error("MetaMask not connected.");
  }

  const provider = new ethersLib.providers.Web3Provider(window.ethereum, "any");
  const signer = provider.getSigner();
  const currentNetwork = await provider.getNetwork();

  if (deployData?.chainId) {
    if (Number(currentNetwork.chainId) !== Number(deployData.chainId)) {
      throw new Error(
        `Connected chainId ${currentNetwork.chainId} does not match target chainId ${deployData.chainId}. Switch network in MetaMask and retry.`
      );
    }
  }

  addMessage("ai", "Opening MetaMask to confirm contract deployment...");

  const factory = new ethersLib.ContractFactory(
    deployData.abi,
    deployData.bytecode,
    signer
  );
  const contract = await factory.deploy(...constructorArgs);
  const txHash = contract.deployTransaction?.hash;

  if (txHash) {
    addMessage("ai", `Deployment transaction sent. Hash: ${txHash}`);
    try {
      onTransactionSent?.({
        txHash,
        chainId: Number(deployData?.chainId || currentNetwork.chainId),
        contractName: deployData?.contractName,
      });
    } catch {
      
    }
  }

  const receipt = await contract.deployTransaction.wait();
  const deployedAddress = receipt?.contractAddress || contract.address;
  if (deployedAddress) {
    addMessage("ai", `Contract deployed at: ${deployedAddress}`);
  }

  return {
    txHash,
    contractAddress: deployedAddress,
  };
}
