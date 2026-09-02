pragma circom 2.0.0;

include "node_modules/circomlib/circuits/poseidon.circom";

// A prototype circuit that commits to a 512-dimensional face embedding.
// In a production environment, this would use a proper Poseidon sponge or 
// Merkle tree. Here we demonstrate a rolling hash commitment for simplicity.
template EmbeddingCommitment(n) {
    signal input embedding[n];
    signal output commitment;

    component hashers[n];
    
    // Initialize first hash with 0 and the first element
    hashers[0] = Poseidon(2);
    hashers[0].inputs[0] <== 0;
    hashers[0].inputs[1] <== embedding[0];

    for (var i = 1; i < n; i++) {
        hashers[i] = Poseidon(2);
        hashers[i].inputs[0] <== hashers[i-1].out;
        hashers[i].inputs[1] <== embedding[i];
    }

    commitment <== hashers[n-1].out;
}

// Instantiate the component for a 512-d ArcFace embedding
component main = EmbeddingCommitment(512);
