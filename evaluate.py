import torch
import torch.nn.functional as F
from tqdm import tqdm

from utils.dice_score import multiclass_dice_coeff, dice_coeff


@torch.inference_mode()
def evaluate(net, dataloader, device, amp):
    net.eval()
    num_val_batches = len(dataloader)
    dice_score = 0

    # iterate over the validation set
    with torch.autocast(device.type if device.type != 'mps' else 'cpu', enabled=amp):
        for batch in tqdm(dataloader, total=num_val_batches, desc='Validation round', unit='batch', leave=False):
            image, mask_true = batch['image'], batch['mask']

            # move images and labels to correct device and type
            image = image.to(device=device, dtype=torch.float32, memory_format=torch.channels_last)
            mask_true = mask_true.to(device=device, dtype=torch.long)

            # predict the mask
            mask_pred = net(image)

            if net.n_classes == 1:
              # Defensive type check
              assert isinstance(mask_pred, torch.Tensor), f"mask_pred is not a Tensor, got: {type(mask_pred)}"
              assert isinstance(mask_true, torch.Tensor), f"mask_true is not a Tensor, got: {type(mask_true)}"

              if mask_pred.ndim == 3:
                  mask_pred = mask_pred.unsqueeze(1)
              if mask_true.ndim == 3:
                  mask_true = mask_true.unsqueeze(1)

              mask_true = mask_true.to(device=device, dtype=torch.float32)
              mask_pred = torch.sigmoid(mask_pred)

              assert mask_true.size() == mask_pred.size(), \
                  f"Shape mismatch in dice_coeff: pred {mask_pred.shape}, true {mask_true.shape}"

              dice_score += dice_coeff(mask_pred, mask_true, reduce_batch_first=False)
            else:
                assert mask_true.min() >= 0 and mask_true.max() < net.n_classes, 'True mask indices should be in [0, n_classes['
                # convert to one-hot format
                mask_true = F.one_hot(mask_true, net.n_classes).permute(0, 3, 1, 2).float()
                mask_pred = F.one_hot(mask_pred.argmax(dim=1), net.n_classes).permute(0, 3, 1, 2).float()
                # compute the Dice score, ignoring background
                dice_score += multiclass_dice_coeff(mask_pred[:, 1:], mask_true[:, 1:], reduce_batch_first=False)

    net.train()
    return dice_score / max(num_val_batches, 1)
