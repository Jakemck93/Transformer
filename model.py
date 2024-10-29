import torch 
import torch.nn as nn
import math 

class InputEmbedding(nn.Module):
    #this class takes in two parameters: d_model and vocab_size. 
    #d_model is the dimension of the embedding vector, in this case we follow the paper(Attention is all you need) and set it to 512.
    #vocab_size is the size of the vocabulary, this is determined by the size of the dataset we are using.
    def __init__(self, d_model: int, vocab_size:int) -> None:
        super().__init__()
        self.d_model = d_model
        self.vocab_size = vocab_size
        #nn.Embedding is a class that takes in two parameters: vocab_size and d_model, and creates input embeddings.
        #Input embeddings are a way to represent words as vectors of numbers.
        #Each word is represented as a vector of size d_model.
        #So if we have 1000 words, in our vocab. we will end up with a matrix of size 1000x512(512 coming from d_model.
        #These values are randomly initialized and then trained during the training process.
        self.embedding = nn.Embedding(vocab_size, d_model)
    def forward(self, x):
        #this returns our embeddings, which are multiplied by the sqrt of d_model
        #this prevents the embeddings from becoming to large 
        #our output will be a tensor with the shape (batch_size, seq_len, d_model)
        #Batch size is the number of sequences in a batch, how many sequences are we processing at once.
            #Batch size is a parameter we set later during training
        #Seq_len is the length of the sequence, how long is the sequence we are processing.
        #d_model is the dimension of the embedding vector
        return self.embedding(x) * math.sqrt(self.d_model)

class PositionalEncoding(nn.Module):
    #Posistional Encoding is a way to add information about the position of the words in the sequence.
    #When we converted to embeddings we lost the position of the words in the sequence.
    #Positional Encoding is a way to add information about the position of the words in the sequence.
    #It uses alternating sin and cosine functions of different frequencies to create a unique encoding for each position in the sequence.
    def __init__(self, d_model: int, seq_len: int, dropout: float) -> None:
        super().__init__()
        self.d_model = d_model
        self.seq_len = seq_len
        self.dropout = nn.Dropout(dropout)

        #create a matrix of shape (seq_len, d_model)
        pe = torch.zeros(seq_len, d_model)
        #create a vector of shape (Seq_len, 1)
        position = torch.arange(0, seq_len, dtype=torch.float).unsqueeze(1)
        #creates a sequence of even numbers from 0 to d_model
        #multiplies each by (-log(10000.0) / d_model)
        #takes the exponential of each element
        #this creates a sequence of wavelengths for the sine and cosine functions
        #the wavelengths increase exponentially as we move down the sequence
        #this allows the model to capture both short and long range dependencies
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        #apply sin to even postions, cos to odd
        pe[:,0::2] = torch.sin(position * div_term)
        pe[:,1::2] = torch.cos(position * div_term)
        #add a batch dimension to the pe matrix
        #this is because the pe matrix is a 2D matrix, but we want to add it to the input tensor
        #which is a 3D tensor
        pe = pe.unsqueeze(0) #(1, Seq_Len, d_model)
        #register the pe matrix as a buffer
        #this means that the pe matrix will be saved as part of the model's state dict
        #but will not be considered a parameter of the model
        #this is because the pe matrix is not a parameter of the model, it is a constant
        self.register_buffer('pe',pe)

    def forward(self,x):
        #self.pe[:, :x.shape[1], :] is a slice of the pe matrix
        #:, is the first dimension of the pe matrix, which is the batch size
        #:x.shape[1] is the second dimension of the pe matrix, which is the sequence length
        #: is the third dimension of the pe matrix, which is the d_model
        #for example, if:
            #our pe buffer is shape (1,512,256), 1 is the batch size, 512 is the sequence length, 256 is the d_model
            #and our x is shape (32, 20, 256), 1 is the batch size, 10 is the sequence length, 256 is the d_model
            #the slice will be (1, 10, 256), matching our input shape
        x = x + (self.pe[:, :x.shape[1],:]).requires_grad_(False)
        return self.dropout(x)
class LayerNormalization(nn.Module):
    #Layer Normalization is a way to normalize the inputs to a layer.
    #It is used to normalize the inputs to a layer, so that the inputs to a layer have a mean of 0 and a standard deviation of 1.
    #This is done to prevent the inputs to a layer from becoming too large or too small.
    def __init__(self, eps: float = 10**-6) -> None:
        super().__init__()
        self.eps = eps
        #create two parameters, alpha and bias
        #these are parameters that will be learned during training
        #they are used to scale and shift the normalized inputs
        #eps is a small value added to the denominator to prevent division by zero
        self.alpha = nn.Parameter(torch.ones(1))
        self.bias = nn.Parameter(torch.zeros(1))

    def forward(self,x):
        mean = x.mean(dim = -1, keepdim=True)
        std = x.std(dim = -1, keepdim= True)
        return self.alpha * (x - mean) / (std + self.eps) + self.bias
    
class FeedForwardBlock(nn.Module):

    def __init__(self, d_model: int, d_ff: int, dropout: float) -> None:
        super().__init__()
        self.linear_1 = nn.Linear(d_model, d_ff)
        self.dropout = nn.Dropout(dropout)
        self.linear_2 = nn.Linear(d_ff, d_model)

    def forward(self, x):
        #(Batch, Seq_len, d_model) --> (Batch, Seq_len, d_ff) --> (Batch, Seq_len, d_model)
        return self.linear_2(self.dropout(torch.relu(self.linear_1(x))))
class MultiHeadAttentionBlock(nn.Module):

    def __init__(self, d_model: int, h: int, dropout: float) -> None:
        super().__init__()
        self.d_model = d_model
        self.h = h
        assert d_model % h == 0, "d_model is not divisible by h"
        
        self.d_k = d_model // h 
        self.w_q = nn.Linear(d_model, d_model) #wq
        self.w_k = nn.Linear(d_model, d_model) #wk
        self.w_v = nn.Linear(d_model, d_model) #wv

        self.w_o = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)
    
    @staticmethod
    def attention(query, key, value, mask, dropout: nn.Dropout):
        d_k = query.shape[-1]

        #(Batch, h, Seq_Len, d_k) --> (Batch, h, Seq_Len, Seq_len)
        attention_scores = (query @ key.transpose(-2,-1)) / math.sqrt(d_k)
        if mask is not None:
            attention_scores.masked_fill_(mask == 0, -1e9)
        attention_scores = attention_scores.softmax(dim = -1) #(Batch, h, Seq_len, Seq_len)
        if dropout is not None:
            attention_scores - dropout(attention_scores)
        
        return (attention_scores @ value), attention_scores

    def forward(self, q, k, v, mask):
        query = self.w_q(q) #(Batch, Seq_len, d_model) --> (Batch, Seq_Len, d_model)
        key = self.w_k(k) #(Batch, Seq_len, d_model) --> (Batch, Seq_Len, d_model)
        value = self.w_v(v) #(Batch, Seq_len, d_model) --> (Batch, Seq_Len, d_model)

        #(Batch, Seq_Len, d_model) --> (Batch, Seq_Len, h, d_k) --> Batch, h, Seq_len, d_k)
        #query = query.view(query.shape[0], query.shape[1], self.h, self.d_k).transpose(1,2)
        #key = query.view(key.shape[0], key.shape[1], self.h, self.d_k).transpose(1,2)
        #value = query.view(value.shape[0], value.shape[1], self.h, self.d_k).transpose(1,2)

        query = query.contiguous().view(query.shape[0], -1, self.h, self.d_k).transpose(1, 2)
        key = key.contiguous().view(key.shape[0], -1, self.h, self.d_k).transpose(1, 2)
        value = value.contiguous().view(value.shape[0], -1, self.h, self.d_k).transpose(1, 2)


        x, self.attention_scores = MultiHeadAttentionBlock.attention(query, key, value, mask, self.dropout)
        x = x.transpose(1, 2).contiguous().view(x.shape[0], -1, self.h * self.d_k)

        #(Batch, Seq_Len, d_model) --> (Batch, Seq_Len, d_model)
        return self.w_o(x)

class ResidualConnection(nn.Module):
    def __init__(self, dropout: float) -> None:
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        self.norm = LayerNormalization()

    def forward(self, x, sublayer):
        return x + self.dropout(sublayer(self.norm(x)))

class EncoderBlock(nn.Module):
    def __init__(self, self_attention_block: MultiHeadAttentionBlock, feed_forward_block: FeedForwardBlock, dropout: float) -> None:
        super().__init__()
        self.self_attention_block = self_attention_block
        self.feed_forward_block = feed_forward_block
        self.residual_connections = nn.ModuleList([ResidualConnection(dropout) for _ in range(2)])
    
    def forward(self, x , src_mask):
        x = self.residual_connections[0](x, lambda x: self.self_attention_block(x, x, x, src_mask))
        x = self.residual_connections[1](x, self.feed_forward_block)
        return x 

class Encoder(nn.Module):
    def __init__(self, layers: nn.ModuleList) -> None:
        super().__init__()
        self.layers = layers
        self.norm = LayerNormalization()

    def forward(self, x, mask):
        for layer in self.layers:
            x = layer(x, mask)
        return self.norm(x)

class DecoderBlock(nn.Module):
    def __init__(self, self_attention_block: MultiHeadAttentionBlock, cross_attention_block: MultiHeadAttentionBlock, feed_forward_block: FeedForwardBlock, dropout: float) -> None:
        super().__init__()
        self.self_attention_block = self_attention_block
        self.cross_attention_block = cross_attention_block
        self.feed_forward_block = feed_forward_block
        self.residual_connection = nn.ModuleList([ResidualConnection(dropout) for _ in range(3)])

    def forward(self, x, encoder_output, src_mask, tgt_mask):
        x = self.residual_connection[0](x, lambda x: self.self_attention_block(x, x, x, tgt_mask))
        x = self.residual_connection[1](x, lambda x: self.cross_attention_block(x, encoder_output, encoder_output, src_mask))
        x = self.residual_connection[2](x, self.feed_forward_block)

        return x 

class Decoder(nn.Module):
    def __init__(self, layers: nn.ModuleList) -> None:
        super().__init__()
        self.layers = layers
        self.norm = LayerNormalization()
    def forward(self, x, encoder_output, src_mask, tgt_mask):
        for layer in self.layers:
            x = layer(x, encoder_output, src_mask, tgt_mask)
        return self.norm(x)

class ProjectionLayer(nn.Module):
    def __init__(self, d_model: int, vocab_size: int) -> None:
        super().__init__()
        self.proj = nn.Linear(d_model, vocab_size)
    
    # (Batch, Seq_Len, d_model) --> (Batch, Seq_Len, Vocab_Size)
    def forward(self, x):
        return torch.log_softmax(self.proj(x), dim = -1)

class Transformer(nn.Module):
    def __init__(self, encoder: Encoder, decoder: Decoder, src_embed: InputEmbedding, tgt_embed: InputEmbedding, src_pos: PositionalEncoding, tgt_pos: PositionalEncoding, projection_layer: ProjectionLayer) -> None:
        super().__init__()
        self.encoder = encoder
        self.decoder = decoder
        self.src_embed = src_embed
        self.tgt_embed = tgt_embed
        self.src_pos = src_pos
        self.tgt_pos = tgt_pos
        self.projection_layer = projection_layer
    
    def encode(self, src, src_mask):
        src = self.src_embed(src)
        src = self.src_pos(src)
        return self.encoder(src, src_mask)

    def decode(self, encoder_output, src_mask, tgt, tgt_mask):
        tgt = self.tgt_embed(tgt)
        tgt = self.tgt_pos(tgt)
        return self.decoder(tgt, encoder_output, src_mask, tgt_mask)

    def project(self, x):
        return self.projection_layer(x)

def build_transformer(src_vocab_size: int, tgt_vocab_size: int, src_seq_len: int, tgt_seq_len: int, d_model: int = 512, N: int = 6, h: int = 8, dropout: float = 0.1, d_ff: int = 2048):
    #Create the embedding layers
    src_embed = InputEmbedding(d_model, src_vocab_size)
    tgt_embed = InputEmbedding(d_model, tgt_vocab_size)

    #Create the positional encoding layers
    src_pos = PositionalEncoding(d_model, src_seq_len, dropout)
    tgt_pos = PositionalEncoding(d_model, tgt_seq_len, dropout)
    
    #Create the encoder blocks 
    encoder_blocks = []
    for _ in range(N):
        encoder_self_attention_block = MultiHeadAttentionBlock(d_model, h, dropout)
        feed_forward_block = FeedForwardBlock(d_model, d_ff, dropout)
        encoder_block = EncoderBlock(encoder_self_attention_block, feed_forward_block, dropout)
        encoder_blocks.append(encoder_block)

    decoder_blocks = []
    for _ in range(N):
        decoder_self_attention_block = MultiHeadAttentionBlock(d_model, h, dropout)
        decoder_cross_attention_block = MultiHeadAttentionBlock(d_model, h, dropout)
        feed_forward_block = FeedForwardBlock(d_model, d_ff, dropout)
        decoder_block = DecoderBlock(decoder_self_attention_block, decoder_cross_attention_block, feed_forward_block, dropout)
        decoder_blocks.append(decoder_block)

    #Create encoder and decoder
    encoder = Encoder(nn.ModuleList(encoder_blocks))
    decoder = Decoder(nn.ModuleList(decoder_blocks))

    #projection Layer
    projection_layer = ProjectionLayer(d_model, tgt_vocab_size)

    #create the transformer

    transformer = Transformer(encoder,decoder,src_embed,tgt_embed,src_pos,tgt_pos,projection_layer)

    # Intialize the parameters
    for p in transformer.parameters():
        if p.dim() > 1:
            nn.init.xavier_uniform(p)
    return transformer